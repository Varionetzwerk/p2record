import math
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from gi.repository import GLib

from core.settings import Settings
from core.screen_picker import list_monitors, find_monitor, Monitor

SEGMENT_SECS = 5


def _is_wayland() -> bool:
    return bool(os.environ.get('WAYLAND_DISPLAY'))


def _vaapi_device() -> Optional[str]:
    """Return first available VAAPI render node, or None."""
    for p in sorted(Path('/dev/dri').glob('renderD*')):
        if os.access(str(p), os.R_OK | os.W_OK):
            return str(p)
    return None


def _quality_to_vaapi_qp(quality: str) -> int:
    return {'low': 35, 'medium': 28, 'high': 22, 'ultra': 16}.get(quality, 22)


def _quality_to_crf(quality: str) -> int:
    return {'low': 30, 'medium': 26, 'high': 23, 'ultra': 18}.get(quality, 23)


def _resolution_target(resolution: str):
    """Returns (w, h) cap or None for native."""
    return {
        '720p':  (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440),
    }.get(resolution)


class Recorder:
    """FFmpeg-based ring-buffer recorder using the segment muxer.

    On Wayland: uses xdg-desktop-portal → PipeWire → GStreamer → ffmpeg.
    On X11:     uses x11grab → ffmpeg directly.
    Tries VAAPI hardware encoding first, falls back to libx264 software.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._process: Optional[subprocess.Popen] = None
        self._gst_process: Optional[subprocess.Popen] = None
        self._log_file = None
        self._segment_dir: Optional[str] = None
        self._is_recording = False
        self._portal_pending = False       # True while waiting for portal callback
        self._portal_stop_event: Optional[threading.Event] = None
        self._using_vaapi = False
        self._segment_lock = threading.Lock()      # held during save_clip to block cleanup
        self._cleanup_timer_id: Optional[int] = None
        self._monitor_timer_id: Optional[int] = None
        self._crash_count = 0
        self._last_crash_time: float = 0.0

        self.on_state_changed: Optional[Callable[[bool], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_buffer_fill: Optional[Callable[[float], None]] = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._is_recording or self._portal_pending:
            return

        # Clean up any leftover segment dir from a previous crash
        if self._segment_dir:
            shutil.rmtree(self._segment_dir, ignore_errors=True)
            self._segment_dir = None

        if _is_wayland():
            print('[Recorder] Wayland erkannt → PipeWire-Portal wird geöffnet…')
            self._portal_pending = True
            self._portal_stop_event = threading.Event()
            from core.portal import request_screencast_node
            request_screencast_node(self._on_portal_ready, self._portal_stop_event)
            # Async — _on_portal_ready() is called back on the GLib main loop
        else:
            # Run in background thread so time.sleep() in _launch() doesn't block GTK
            threading.Thread(target=self._start_x11, daemon=True).start()

    def stop(self) -> None:
        if not self._is_recording:
            return
        self._is_recording = False

        for tid in [self._cleanup_timer_id, self._monitor_timer_id]:
            if tid:
                GLib.source_remove(tid)
        self._cleanup_timer_id = None
        self._monitor_timer_id = None

        # Signal the portal thread to close the D-Bus session
        if self._portal_stop_event:
            self._portal_stop_event.set()
            self._portal_stop_event = None

        # Stop GStreamer source first so ffmpeg gets EOF and finalises segments
        if self._gst_process:
            try:
                self._gst_process.send_signal(signal.SIGTERM)
                self._gst_process.wait(timeout=5)
            except Exception:
                self._gst_process.kill()
            self._gst_process = None

        if self._process:
            try:
                self._process.send_signal(signal.SIGTERM)
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

        if self._segment_dir:
            shutil.rmtree(self._segment_dir, ignore_errors=True)
            self._segment_dir = None

        self._emit_state(False)
        self._emit_buffer_fill(0.0)

    def save_clip(self, clip_duration: int, game_name: Optional[str] = None) -> Optional[str]:
        """Concatenate recent segments → MP4. Returns file path or None."""
        if not self._segment_dir:
            return None

        with self._segment_lock:
            return self._do_save_clip(clip_duration, game_name)

    def _do_save_clip(self, clip_duration: int, game_name: Optional[str]) -> Optional[str]:
        def _size(p: Path) -> int:
            try:
                return p.stat().st_size
            except OSError:
                return 0

        # Snapshot the segment list BEFORE forcing a cut so we know exactly
        # which files to include (the new post-cut segment is excluded).
        segs_before_cut = sorted(Path(self._segment_dir).glob('seg*.mkv'))

        # Send SIGUSR1 to the FFmpeg process — the segment muxer responds by
        # closing the current (partially-written) segment at the next keyframe
        # and starting a fresh one.  This captures footage right up to now.
        if self._process and self._process.poll() is None:
            try:
                self._process.send_signal(signal.SIGUSR1)
                time.sleep(0.7)  # give FFmpeg time to finalise the segment
            except Exception:
                pass

        # Use only the snapshot set (all finalized now) — naturally excludes
        # the tiny new segment FFmpeg just opened after the cut.
        segments = [s for s in segs_before_cut if _size(s) > 4096]
        if not segments:
            print('[Recorder] save_clip: keine fertigen Segmente — noch kein vollständiges 5-Sekunden-Segment')
            return None

        n_needed = math.ceil(clip_duration / SEGMENT_SECS) + 1
        relevant = segments[-n_needed:]

        output_dir = Path(self._settings.get('output_path'))
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        safe_game = (game_name or 'Unknown').replace('/', '_').replace(' ', '_')
        out_file = output_dir / f'{ts}_{safe_game}.mp4'

        import tempfile as tf
        with tf.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for seg in relevant:
                f.write(f"file '{seg}'\n")
            concat_list = f.name

        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                 '-i', concat_list, '-c', 'copy', str(out_file)],
                capture_output=True, timeout=120,
            )
            if result.returncode == 0 and out_file.exists() and out_file.stat().st_size > 0:
                return str(out_file)
            err = result.stderr.decode(errors='replace').strip()
            print(f'[Recorder] save_clip failed: {err[-300:]}')
            return None
        except Exception as e:
            print(f'[Recorder] save_clip exception: {e}')
            return None
        finally:
            os.unlink(concat_list)

    def get_buffer_fill(self) -> float:
        if not self._segment_dir or not self._is_recording:
            return 0.0
        segs = list(Path(self._segment_dir).glob('seg*.mkv'))
        if not segs:
            return 0.0
        available = len(segs) * SEGMENT_SECS
        buf = self._settings.get('buffer_duration', 120)
        return min(available / buf, 1.0)

    # ── Wayland path ───────────────────────────────────────────────────────────

    def _on_portal_ready(
        self, node_id: Optional[int], width: int, height: int, pw_fd: int
    ) -> None:
        # Keep _portal_pending = True until _launch_wayland confirms start/failure.
        # This closes the 1-second race window where a second start() could slip in.
        if node_id is None or pw_fd < 0:
            self._portal_pending = False
            self._emit_error(
                'Bildschirm-Freigabe fehlgeschlagen.\n'
                'Bitte im Dialog einen Monitor auswählen und P2-Record erlauben.'
            )
            return
        self._segment_dir = tempfile.mkdtemp(prefix='p2record_')
        vaapi_dev = _vaapi_device()

        fps = self._settings.get('fps', 30)
        quality = self._settings.get('quality', 'high')
        resolution = self._settings.get('resolution', 'native')

        # Apply resolution cap
        target = _resolution_target(resolution)
        cap_w, cap_h = width, height
        if target:
            tw, th = target
            if width > tw or height > th:
                scale = min(tw / width, th / height)
                cap_w = int(width * scale) & ~1   # must be even
                cap_h = int(height * scale) & ~1

        gst_cmd = self._build_gst_cmd(node_id, cap_w, cap_h, fps, pw_fd)
        ffmpeg_cmd = self._build_wayland_ffmpeg_cmd(vaapi_dev, cap_w, cap_h, fps, quality)
        # Run in background so time.sleep() in _launch_wayland doesn't block GTK
        threading.Thread(
            target=self._launch_wayland, args=(gst_cmd, ffmpeg_cmd, pw_fd), daemon=True
        ).start()

    def _build_gst_cmd(
        self, node_id: int, width: int, height: int, fps: int, pw_fd: int
    ) -> List[str]:
        # fd=  → connects to the portal's isolated PipeWire remote (not global server)
        # path= → selects the node within that remote by serial/id
        # videorate → ensures stable fps regardless of compositor output rate
        return [
            'gst-launch-1.0', '-q',
            'pipewiresrc', f'fd={pw_fd}', f'path={node_id}', 'do-timestamp=true',
            '!', 'videoconvert',
            '!', 'videorate',
            '!', f'video/x-raw,format=NV12,width={width},height={height},framerate={fps}/1',
            '!', 'fdsink', 'fd=1',
        ]

    def _build_wayland_ffmpeg_cmd(
        self, vaapi_dev: Optional[str], width: int, height: int, fps: int, quality: str
    ) -> List[str]:
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning']

        if vaapi_dev:
            cmd += ['-vaapi_device', vaapi_dev]

        # Video: index 0
        cmd += ['-f', 'rawvideo', '-pix_fmt', 'nv12',
                '-video_size', f'{width}x{height}',
                '-framerate', str(fps),
                '-i', 'pipe:0']

        # Audio: indices 1 (and optionally 2 for 'both' mode)
        audio_srcs = self._get_audio_sources()
        for src in audio_srcs:
            cmd += ['-f', 'pulse', '-i', src]
        n = len(audio_srcs)

        if vaapi_dev:
            qp = _quality_to_vaapi_qp(quality)
            if n == 2:
                # Mix two audio streams; include hwupload in filter_complex
                cmd += ['-filter_complex',
                        '[0:v]hwupload=extra_hw_frames=64[vout];'
                        '[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                        '-map', '[vout]', '-map', '[aout]']
            else:
                cmd += ['-vf', 'hwupload=extra_hw_frames=64']
            cmd += ['-c:v', 'h264_vaapi', '-qp', str(qp),
                    '-g', str(fps * SEGMENT_SECS)]
        else:
            crf = _quality_to_crf(quality)
            if n == 2:
                cmd += ['-filter_complex',
                        '[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                        '-map', '0:v', '-map', '[aout]']
            cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(crf),
                    '-g', str(fps * SEGMENT_SECS),
                    '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_SECS})']

        if n > 0:
            cmd += ['-c:a', 'aac', '-b:a', '128k']

        cmd += self._segment_output()
        return cmd

    def _get_audio_sources(self) -> List[str]:
        """Return list of PulseAudio source names (0–2 entries)."""
        mode = self._settings.get('audio_source', 'none')
        if mode == 'none':
            return []
        desktop = self._get_desktop_monitor()
        if mode == 'mic':
            return ['default']
        if mode == 'desktop':
            return [desktop] if desktop else []
        if mode == 'both':
            srcs: List[str] = []
            if desktop:
                srcs.append(desktop)
            srcs.append('default')  # mic
            return srcs
        return []

    def _get_desktop_monitor(self) -> Optional[str]:
        """Return PulseAudio monitor source for the default output sink."""
        try:
            r = subprocess.run(['pactl', 'get-default-sink'],
                               capture_output=True, text=True, timeout=3)
            sink = r.stdout.strip()
            if sink:
                return f'{sink}.monitor'
        except Exception:
            pass
        return None

    def _launch_wayland(
        self, gst_cmd: List[str], ffmpeg_cmd: List[str], pw_fd: int
    ) -> None:
        # Runs in a background thread — use GLib.idle_add for GTK/GLib calls.
        print(f'[Recorder] GStreamer: {" ".join(gst_cmd)}')
        print(f'[Recorder] FFmpeg:    {" ".join(ffmpeg_cmd)}')
        try:
            log_path = '/tmp/p2record_ffmpeg.log'
            self._log_file = open(log_path, 'w')

            self._gst_process = subprocess.Popen(
                gst_cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=self._log_file,
                pass_fds=(pw_fd,),   # inherit the PipeWire remote fd
            )
            # Close pw_fd in parent — child has its own copy via pass_fds
            try:
                os.close(pw_fd)
            except OSError:
                pass

            self._process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=self._gst_process.stdout,
                stdout=self._log_file,
                stderr=self._log_file,
            )
            # Let gst own the write end of the pipe so ffmpeg gets EOF on gst exit
            self._gst_process.stdout.close()

        except FileNotFoundError as e:
            self._portal_pending = False
            GLib.idle_add(lambda: self._emit_error(f'Programm nicht gefunden: {e.filename}') or False)
            return

        import time
        time.sleep(1.0)

        if self._gst_process.poll() is not None or self._process.poll() is not None:
            try:
                err = open('/tmp/p2record_ffmpeg.log').read().strip()
                lines = [l for l in err.splitlines() if l.strip()]
                msg = lines[-1] if lines else 'Start fehlgeschlagen'
            except Exception:
                msg = 'Wayland-Aufnahme-Start fehlgeschlagen'
            print(f'[Recorder] Wayland start failed: {msg}')
            self._portal_pending = False
            GLib.idle_add(lambda: self._emit_error(msg) or False)
            return

        # Clear pending flag and set recording — order matters to avoid race
        self._portal_pending = False
        self._is_recording = True
        enc = 'VAAPI' if _vaapi_device() else 'Software'
        print(f'[Recorder] Aufnahme gestartet (Wayland/PipeWire, {enc})')
        GLib.idle_add(lambda: self._emit_state(True) or False)
        # GLib.timeout_add* is thread-safe — sources execute on the main loop
        self._cleanup_timer_id = GLib.timeout_add(2000, self._cleanup_segments)
        self._monitor_timer_id = GLib.timeout_add(1000, self._monitor_process)

    # ── X11 path ───────────────────────────────────────────────────────────────

    def _start_x11(self) -> None:
        self._segment_dir = tempfile.mkdtemp(prefix='p2record_')
        vaapi_dev = _vaapi_device()
        if vaapi_dev:
            cmd = self._build_vaapi_cmd(vaapi_dev)
            if self._launch(cmd, vaapi=True):
                return
        cmd = self._build_software_cmd()
        self._launch(cmd, vaapi=False)

    def _get_monitor(self) -> Optional[Monitor]:
        monitors = list_monitors()
        name = self._settings.get('capture_monitor', '')
        if name:
            mon = find_monitor(name, monitors)
            if mon:
                return mon
        for m in monitors:
            if m.primary:
                return m
        return monitors[0] if monitors else None

    def _video_input(self, fps: int) -> List[str]:
        display = os.environ.get('DISPLAY', ':0')
        mon = self._get_monitor()
        base = ['-f', 'x11grab', '-framerate', str(fps)]
        if mon:
            base += ['-video_size', f'{mon.width}x{mon.height}',
                     '-i', f'{display}+{mon.x},{mon.y}']
        else:
            base += ['-i', display]
        return base

    def _segment_output(self) -> List[str]:
        pattern = str(Path(self._segment_dir) / 'seg%05d.mkv')
        return [
            '-f', 'segment',
            '-segment_time', str(SEGMENT_SECS),
            '-reset_timestamps', '1',
            '-segment_format', 'matroska',
            pattern,
        ]

    def _build_vaapi_cmd(self, vaapi_dev: str) -> List[str]:
        fps = self._settings.get('fps', 30)
        quality = self._settings.get('quality', 'high')
        qp = _quality_to_vaapi_qp(quality)
        target = _resolution_target(self._settings.get('resolution', 'native'))

        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning']
        cmd += ['-vaapi_device', vaapi_dev]   # must be before inputs
        cmd += self._video_input(fps)          # index 0

        audio_srcs = self._get_audio_sources()
        for src in audio_srcs:
            cmd += ['-f', 'pulse', '-i', src]  # index 1 (and 2 for 'both')
        n = len(audio_srcs)

        vf_parts = ['format=nv12', 'hwupload=extra_hw_frames=64']
        if target:
            vf_parts.append(f'scale_vaapi={target[0]}:-2')
        vf_str = ','.join(vf_parts)

        if n == 2:
            cmd += ['-filter_complex',
                    f'[0:v]{vf_str}[vout];[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                    '-map', '[vout]', '-map', '[aout]']
        else:
            cmd += ['-vf', vf_str]

        cmd += ['-c:v', 'h264_vaapi', '-qp', str(qp), '-g', str(fps * SEGMENT_SECS)]

        if n > 0:
            cmd += ['-c:a', 'aac', '-b:a', '128k']

        cmd += self._segment_output()
        return cmd

    def _build_software_cmd(self) -> List[str]:
        fps = min(self._settings.get('fps', 30), 30)
        quality = self._settings.get('quality', 'high')
        crf = _quality_to_crf(quality)
        target = _resolution_target(self._settings.get('resolution', 'native'))

        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning']
        cmd += self._video_input(fps)          # index 0

        audio_srcs = self._get_audio_sources()
        for src in audio_srcs:
            cmd += ['-f', 'pulse', '-i', src]  # index 1 (and 2 for 'both')
        n = len(audio_srcs)

        vf_scale = f'scale={target[0]}:-2' if target else None

        if n == 2:
            vid_part = f'[0:v]{vf_scale}[vout];' if vf_scale else ''
            vid_map  = '[vout]' if vf_scale else '0:v'
            cmd += ['-filter_complex',
                    f'{vid_part}[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                    '-map', vid_map, '-map', '[aout]']
        elif vf_scale:
            cmd += ['-vf', vf_scale]

        cmd += [
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(crf),
            '-g', str(fps * SEGMENT_SECS),
            '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_SECS})',
        ]

        if n > 0:
            cmd += ['-c:a', 'aac', '-b:a', '128k']

        cmd += self._segment_output()
        return cmd

    # ── Internal ───────────────────────────────────────────────────────────────

    def _launch(self, cmd: List[str], vaapi: bool) -> bool:
        # Runs in a background thread — use GLib.idle_add for GTK/GLib calls.
        print(f'[Recorder] Starting ({"VAAPI" if vaapi else "software"}):')
        print(' ', ' '.join(cmd))
        try:
            log_path = '/tmp/p2record_ffmpeg.log'
            self._log_file = open(log_path, 'w')
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=self._log_file,
                stderr=self._log_file,
            )
        except FileNotFoundError:
            GLib.idle_add(lambda: self._emit_error('ffmpeg nicht gefunden — sudo pacman -S ffmpeg') or False)
            return False

        import time
        time.sleep(0.8)
        if self._process.poll() is not None:
            try:
                err = open('/tmp/p2record_ffmpeg.log').read().strip()
                last = [l for l in err.splitlines() if l.strip()]
                msg = last[-1] if last else 'Unbekannter Fehler'
            except Exception:
                msg = 'FFmpeg-Start fehlgeschlagen'
            print(f'[Recorder] FFmpeg failed: {msg}')
            if vaapi:
                print('[Recorder] VAAPI fehlgeschlagen, versuche Software-Encoding…')
            return False

        self._using_vaapi = vaapi
        self._is_recording = True
        enc = 'VAAPI (h264)' if vaapi else 'Software (libx264, 30fps)'
        print(f'[Recorder] Aufnahme gestartet mit {enc}')
        GLib.idle_add(lambda: self._emit_state(True) or False)
        # GLib.timeout_add* is thread-safe — sources execute on the main loop
        self._cleanup_timer_id = GLib.timeout_add(2000, self._cleanup_segments)
        self._monitor_timer_id = GLib.timeout_add(1000, self._monitor_process)
        return True

    def _cleanup_segments(self) -> bool:
        if not self._segment_dir or not self._is_recording:
            return False
        if not self._segment_lock.acquire(blocking=False):
            return True  # save_clip holds the lock, retry next tick
        try:
            buf = self._settings.get('buffer_duration', 120)
            # +2: segment currently being written + safety margin for save_clip
            max_segs = math.ceil(buf / SEGMENT_SECS) + 2
            segs = sorted(Path(self._segment_dir).glob('seg*.mkv'))
            if len(segs) > max_segs:
                for old in segs[:-max_segs]:
                    old.unlink(missing_ok=True)
            self._emit_buffer_fill(self.get_buffer_fill())
        finally:
            self._segment_lock.release()
        return True

    def _monitor_process(self) -> bool:
        gst_dead = self._gst_process and self._gst_process.poll() is not None
        ffmpeg_dead = self._process and self._process.poll() is not None

        if gst_dead or ffmpeg_dead:
            self._is_recording = False
            self._process = None
            self._gst_process = None
            self._cleanup_timer_id = None
            self._monitor_timer_id = None
            if self._segment_dir:
                shutil.rmtree(self._segment_dir, ignore_errors=True)
                self._segment_dir = None

            # Stop old Wayland portal session so the restart can create a fresh one
            if self._portal_stop_event:
                self._portal_stop_event.set()
                self._portal_stop_event = None

            self._emit_state(False)
            self._emit_buffer_fill(0.0)

            now = time.time()
            if now - self._last_crash_time > 60:
                self._crash_count = 0
            self._last_crash_time = now
            self._crash_count += 1

            if self._crash_count <= 3:
                msg = f'Aufnahme unterbrochen – Neustart {self._crash_count}/3…'
                print(f'[Recorder] {msg}')
                self._emit_error(msg)
                GLib.timeout_add_seconds(3, self._auto_restart)
            else:
                self._crash_count = 0
                msg = 'Aufnahme unterbrochen – zu viele Abstürze'
                try:
                    log = open('/tmp/p2record_ffmpeg.log').read()
                    lines = [l for l in log.splitlines() if l.strip()]
                    if lines:
                        msg = f'FFmpeg: {lines[-1]}'
                except Exception:
                    pass
                print(f'[Recorder] Zu viele Abstürze — gebe auf: {msg}')
                self._emit_error(msg)
            return False
        return True

    def _auto_restart(self) -> bool:
        if not self._is_recording and not self._portal_pending:
            print('[Recorder] Auto-Neustart…')
            self.start()
        return False

    def _emit_state(self, recording: bool) -> None:
        if self.on_state_changed:
            self.on_state_changed(recording)

    def _emit_error(self, msg: str) -> None:
        if self.on_error:
            self.on_error(msg)

    def _emit_buffer_fill(self, fill: float) -> None:
        if self.on_buffer_fill:
            self.on_buffer_fill(fill)
