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


# Probe results per render node — a device file existing does NOT mean VAAPI
# encoding works there (NVIDIA exposes /dev/dri too, VMs have virgl, …).
_VAAPI_PROBED: dict = {}


def _vaapi_encode_works(dev: str) -> bool:
    """Tiny 2-frame test encode through the exact filter chain we use."""
    if dev in _VAAPI_PROBED:
        return _VAAPI_PROBED[dev]
    try:
        r = subprocess.run(
            ['ffmpeg', '-hide_banner', '-loglevel', 'error',
             '-vaapi_device', dev,
             '-f', 'lavfi', '-i', 'color=black:size=320x240:rate=30',
             '-frames:v', '2',
             '-vf', 'format=bgr0,hwupload,scale_vaapi=format=nv12',
             '-c:v', 'h264_vaapi', '-f', 'null', '-'],
            capture_output=True, timeout=15,
        )
        ok = r.returncode == 0
    except Exception:
        ok = False
    _VAAPI_PROBED[dev] = ok
    if not ok:
        print(f'[Recorder] VAAPI-Probe fehlgeschlagen für {dev}')
    return ok


def _vaapi_device() -> Optional[str]:
    """Return first render node with WORKING H264 VAAPI encoding, or None.

    May block ~1 s per node on first call (probe) — call from a background
    thread, results are cached afterwards.
    """
    for p in sorted(Path('/dev/dri').glob('renderD*')):
        if os.access(str(p), os.R_OK | os.W_OK) and _vaapi_encode_works(str(p)):
            return str(p)
    return None


_DRAWTEXT_PROBED: Optional[bool] = None


def _drawtext_works() -> bool:
    """drawtext needs fontconfig in the FFmpeg build — probe once, cache."""
    global _DRAWTEXT_PROBED
    if _DRAWTEXT_PROBED is None:
        try:
            r = subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error',
                 '-f', 'lavfi', '-i', 'color=black:size=320x240:rate=30',
                 '-frames:v', '1',
                 '-vf', "drawtext=text='%{localtime\\:%T}':fontsize=20",
                 '-f', 'null', '-'],
                capture_output=True, timeout=15,
            )
            _DRAWTEXT_PROBED = r.returncode == 0
        except Exception:
            _DRAWTEXT_PROBED = False
        if not _DRAWTEXT_PROBED:
            print('[Recorder] drawtext nicht verfügbar — Zeitstempel-Overlay deaktiviert')
    return _DRAWTEXT_PROBED


# Timestamp overlay position → drawtext x/y expressions (16 px margin)
_TS_POSITIONS = {
    'top-left':      ('16',            '16'),
    'top-center':    ('(w-text_w)/2',  '16'),
    'top-right':     ('w-text_w-16',   '16'),
    'bottom-left':   ('16',            'h-text_h-16'),
    'bottom-center': ('(w-text_w)/2',  'h-text_h-16'),
    'bottom-right':  ('w-text_w-16',   'h-text_h-16'),
}


_NVENC_PROBED: Optional[bool] = None


def _nvenc_works() -> bool:
    """NVIDIA hardware encoder available? (No VAAPI there — NVENC instead.)"""
    global _NVENC_PROBED
    if _NVENC_PROBED is None:
        try:
            r = subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error',
                 '-f', 'lavfi', '-i', 'color=black:size=320x240:rate=30',
                 '-frames:v', '2', '-vf', 'format=nv12',
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                capture_output=True, timeout=15,
            )
            _NVENC_PROBED = r.returncode == 0
        except Exception:
            _NVENC_PROBED = False
        if not _NVENC_PROBED:
            print('[Recorder] NVENC nicht verfügbar')
    return _NVENC_PROBED


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
        self._restart_timer_id: Optional[int] = None
        # Sticky for the session: once VAAPI failed at launch, stay on software
        self._force_software = False

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
        # Cancel any pending auto-restart — a manual stop must win over it
        if self._restart_timer_id:
            GLib.source_remove(self._restart_timer_id)
            self._restart_timer_id = None
        self._crash_count = 0
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
        # Snapshot — stop()/_monitor_process may null _segment_dir mid-save
        seg_dir = self._segment_dir
        if not seg_dir:
            return None

        def _size(p: Path) -> int:
            try:
                return p.stat().st_size
            except OSError:
                return 0

        # All segment files, sorted by sequence number.
        all_segs = sorted(Path(seg_dir).glob('seg*.mkv'))

        # Exclude the last file — it is currently being written by FFmpeg and
        # may have incomplete MKV framing.  All others are fully closed.
        # Also filter out any unexpectedly tiny files (< 4096 bytes).
        complete = [s for s in all_segs[:-1] if _size(s) > 4096]

        if not complete:
            print('[Recorder] save_clip: no completed segments yet')
            return None

        n_needed = math.ceil(clip_duration / SEGMENT_SECS) + 1
        relevant = complete[-n_needed:]

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
        segs = sorted(Path(self._segment_dir).glob('seg*.mkv'))
        if not segs:
            return 0.0
        buf = self._settings.get('buffer_duration', 120)
        buf_segs = math.ceil(buf / SEGMENT_SECS)
        n = len(segs)
        if n < buf_segs:
            # Initial fill: 0 % → 100 %
            return n / buf_segs
        # Buffer full — show ring-buffer cycling so the bar resets each full rotation.
        # Use the sequence number of the newest segment modulo buf_segs.
        # Mapping: seq 1..buf_segs → 1/buf_segs..1.0, then repeats.
        try:
            last_num = int(segs[-1].stem[3:])          # "seg00042" → 42
            cycle_pos = (last_num - 1) % buf_segs + 1  # 1 … buf_segs
            return cycle_pos / buf_segs
        except (ValueError, IndexError):
            return 1.0

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
        if width <= 0 or height <= 0:
            # Some portals return no stream size — fall back to Full HD
            width, height = 1920, 1080

        self._segment_dir = tempfile.mkdtemp(prefix='p2record_')

        fps = self._settings.get('fps', 30)
        quality = self._settings.get('quality', 'high')
        resolution = self._settings.get('resolution', 'native')

        # Resolution cap → scaling happens on the GPU (scale_vaapi) or in
        # FFmpeg swscale — never in GStreamer on the CPU
        target = _resolution_target(resolution)
        cap = None
        if target:
            tw, th = target
            if width > tw or height > th:
                scale = min(tw / width, th / height)
                cap = (int(width * scale) & ~1,   # must be even
                       int(height * scale) & ~1)

        # Run in background: the VAAPI probe and time.sleep() in
        # _launch_wayland must not block GTK
        threading.Thread(
            target=self._launch_wayland,
            args=(node_id, width, height, cap, fps, quality, pw_fd),
            daemon=True,
        ).start()

    def _build_gst_cmd(
        self, node_id: int, width: int, height: int, fps: int, pw_fd: int
    ) -> List[str]:
        # fd=  → connects to the portal's isolated PipeWire remote (not global server)
        # path= → selects the node within that remote by serial/id
        # BGRx caps → compositors deliver BGRx natively, so videoconvert is a
        #   passthrough. The expensive BGRx→NV12 conversion (and scaling) runs
        #   on the GPU in FFmpeg (hwupload + scale_vaapi) — a CPU videoconvert
        #   here can't keep 60 fps on small CPUs and caused stuttery clips.
        # videorate → ensures stable fps regardless of compositor output rate
        # queue → decouples capture from pipe writes; drops oldest on overload
        #   instead of stalling the whole PipeWire stream
        return [
            'gst-launch-1.0', '-q',
            'pipewiresrc', f'fd={pw_fd}', f'path={node_id}', 'do-timestamp=true',
            '!', 'videoconvert',
            '!', 'videoscale',
            '!', 'videorate',
            '!', f'video/x-raw,format=BGRx,width={width},height={height},framerate={fps}/1',
            '!', 'queue', 'max-size-buffers=4', 'max-size-bytes=0', 'max-size-time=0', 'leaky=downstream',
            '!', 'fdsink', 'fd=1',
        ]

    def _build_wayland_ffmpeg_cmd(
        self, enc: str, vaapi_dev: Optional[str], width: int, height: int,
        cap: Optional[tuple], fps: int, quality: str
    ) -> List[str]:
        """enc: 'vaapi' | 'nvenc' | 'software'"""
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning']

        if enc == 'vaapi':
            cmd += ['-vaapi_device', vaapi_dev]

        # Video: index 0 — raw BGRx straight from the compositor (no CPU csc)
        cmd += ['-f', 'rawvideo', '-pix_fmt', 'bgr0',
                '-video_size', f'{width}x{height}',
                '-framerate', str(fps),
                '-i', 'pipe:0']

        # Audio: indices 1 (and optionally 2 for 'both' mode)
        audio_srcs = self._get_audio_sources()
        for src in audio_srcs:
            cmd += ['-f', 'pulse', '-i', src]
        n = len(audio_srcs)

        qp = _quality_to_vaapi_qp(quality)
        if enc == 'vaapi':
            # BGRx→NV12 conversion and scaling run on the GPU (scale_vaapi)
            if cap:
                vf = ('hwupload=extra_hw_frames=64,'
                      f'scale_vaapi=w={cap[0]}:h={cap[1]}:format=nv12')
            else:
                vf = 'hwupload=extra_hw_frames=64,scale_vaapi=format=nv12'
            codec = ['-c:v', 'h264_vaapi', '-qp', str(qp),
                     '-g', str(fps * SEGMENT_SECS)]
        elif enc == 'nvenc':
            # NVIDIA: convert on the CPU (cheap), encode on the GPU (NVENC)
            vf = (f'scale={cap[0]}:{cap[1]},' if cap else '') + 'format=nv12'
            codec = ['-c:v', 'h264_nvenc', '-rc', 'constqp', '-qp', str(qp),
                     '-g', str(fps * SEGMENT_SECS)]
        else:
            crf = _quality_to_crf(quality)
            # Software fallback: convert/scale/encode on the CPU
            vf = (f'scale={cap[0]}:{cap[1]},' if cap else '') + 'format=nv12'
            codec = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(crf),
                     '-g', str(fps * SEGMENT_SECS),
                     '-force_key_frames', f'expr:gte(t,n_forced*{SEGMENT_SECS})']

        # Timestamp overlay draws on the raw frames, before upload/scale
        dt = self._drawtext_filter(height)
        if dt:
            vf = f'{dt},{vf}'

        if n == 2:
            # Mix two audio streams; include the video chain in filter_complex
            cmd += ['-filter_complex',
                    f'[0:v]{vf}[vout];'
                    '[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                    '-map', '[vout]', '-map', '[aout]']
        else:
            cmd += ['-vf', vf]
        cmd += codec

        if n > 0:
            cmd += ['-c:a', 'aac', '-b:a', '128k']

        cmd += self._segment_output()
        return cmd

    def _drawtext_filter(self, height: int) -> Optional[str]:
        """Timestamp overlay (date + time), or None when disabled/unavailable.

        Runs on the raw CPU frames, i.e. must come BEFORE hwupload in the
        filter chain. Text area is tiny, so the CPU cost is negligible.
        """
        pos = self._settings.get('timestamp_position', 'off')
        if pos not in _TS_POSITIONS or not _drawtext_works():
            return None
        x, y = _TS_POSITIONS[pos]
        fontsize = max(16, height // 40)   # scales with capture resolution
        # %T = HH:MM:SS — avoids literal colons, which FFmpeg's option
        # parser would otherwise treat as %{...} argument separators
        return ("drawtext=text='%{localtime\\:%d.%m.%Y %T}':"
                f'fontsize={fontsize}:fontcolor=white:'
                'box=1:boxcolor=black@0.45:boxborderw=8:'
                f'x={x}:y={y}')

    def _monitor_height(self) -> int:
        mon = self._get_monitor()
        return mon.height if mon else 1080

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
        self, node_id: int, width: int, height: int,
        cap: Optional[tuple], fps: int, quality: str, pw_fd: int
    ) -> None:
        # Runs in a background thread — use GLib.idle_add for GTK/GLib calls.
        # Encoder ladder: VAAPI (AMD/Intel) → NVENC (NVIDIA) → libx264
        if self._force_software:
            enc, vaapi_dev = 'software', None
        else:
            vaapi_dev = _vaapi_device()
            enc = 'vaapi' if vaapi_dev else ('nvenc' if _nvenc_works() else 'software')
        if enc == 'software':
            fps = min(fps, 30)   # software encoding can't sustain 60 fps

        gst_cmd = self._build_gst_cmd(node_id, width, height, fps, pw_fd)
        ffmpeg_cmd = self._build_wayland_ffmpeg_cmd(enc, vaapi_dev, width, height, cap, fps, quality)
        print(f'[Recorder] GStreamer: {" ".join(gst_cmd)}')
        print(f'[Recorder] FFmpeg:    {" ".join(ffmpeg_cmd)}')
        try:
            log_path = '/tmp/p2record_ffmpeg.log'
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
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
            self._cleanup_failed_launch()
            self._portal_pending = False
            GLib.idle_add(lambda: self._emit_error(f'Programm nicht gefunden: {e.filename}') or False)
            return

        import time
        time.sleep(1.0)

        if self._gst_process.poll() is not None or self._process.poll() is not None:
            msg = self._last_log_line('Wayland-Aufnahme-Start fehlgeschlagen')
            print(f'[Recorder] Wayland start failed: {msg}')
            self._cleanup_failed_launch()
            self._portal_pending = False
            if enc != 'software':
                # Hardware encoder failed despite the probe (exotic stack) —
                # retry the whole session once with software encoding
                self._force_software = True
                print(f'[Recorder] {enc} fehlgeschlagen — Neuversuch mit Software-Encoding…')
                GLib.idle_add(lambda: self.start() or False)
                return
            GLib.idle_add(lambda: self._emit_error(msg) or False)
            return

        # Clear pending flag and set recording — order matters to avoid race
        self._portal_pending = False
        self._is_recording = True
        label = {'vaapi': 'VAAPI', 'nvenc': 'NVENC', 'software': 'Software'}[enc]
        print(f'[Recorder] Aufnahme gestartet (Wayland/PipeWire, {label})')
        GLib.idle_add(lambda: self._emit_state(True) or False)
        # GLib.timeout_add* is thread-safe — sources execute on the main loop
        self._cleanup_timer_id = GLib.timeout_add(2000, self._cleanup_segments)
        self._monitor_timer_id = GLib.timeout_add(1000, self._monitor_process)

    # ── X11 path ───────────────────────────────────────────────────────────────

    def _start_x11(self) -> None:
        self._segment_dir = tempfile.mkdtemp(prefix='p2record_')
        # Encoder ladder: VAAPI (AMD/Intel) → NVENC (NVIDIA) → libx264
        vaapi_dev = _vaapi_device()
        if vaapi_dev:
            if self._launch(self._build_vaapi_cmd(vaapi_dev), label='VAAPI'):
                return
        elif _nvenc_works():
            if self._launch(self._build_nvenc_cmd(), label='NVENC'):
                return
        self._launch(self._build_software_cmd(), label='Software', emit_on_fail=True)

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

        # x11grab delivers BGRx — upload raw and convert/scale on the GPU
        dt = self._drawtext_filter(self._monitor_height())
        vf_parts = [dt] if dt else []
        vf_parts.append('hwupload=extra_hw_frames=64')
        if target:
            vf_parts.append(f'scale_vaapi=w={target[0]}:h=-2:format=nv12')
        else:
            vf_parts.append('scale_vaapi=format=nv12')
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

    def _build_nvenc_cmd(self) -> List[str]:
        """NVIDIA: convert on the CPU (cheap), encode on the GPU (NVENC)."""
        fps = self._settings.get('fps', 30)
        quality = self._settings.get('quality', 'high')
        qp = _quality_to_vaapi_qp(quality)
        target = _resolution_target(self._settings.get('resolution', 'native'))

        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning']
        cmd += self._video_input(fps)          # index 0

        audio_srcs = self._get_audio_sources()
        for src in audio_srcs:
            cmd += ['-f', 'pulse', '-i', src]  # index 1 (and 2 for 'both')
        n = len(audio_srcs)

        dt = self._drawtext_filter(self._monitor_height())
        vf = ((dt + ',') if dt else '') \
            + (f'scale={target[0]}:-2,' if target else '') + 'format=nv12'
        if n == 2:
            cmd += ['-filter_complex',
                    f'[0:v]{vf}[vout];[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                    '-map', '[vout]', '-map', '[aout]']
        else:
            cmd += ['-vf', vf]

        cmd += ['-c:v', 'h264_nvenc', '-rc', 'constqp', '-qp', str(qp),
                '-g', str(fps * SEGMENT_SECS)]

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

        dt = self._drawtext_filter(self._monitor_height())
        vf_parts = [p for p in (dt, f'scale={target[0]}:-2' if target else None) if p]
        vf_str = ','.join(vf_parts) if vf_parts else None

        if n == 2:
            vid_part = f'[0:v]{vf_str}[vout];' if vf_str else ''
            vid_map  = '[vout]' if vf_str else '0:v'
            cmd += ['-filter_complex',
                    f'{vid_part}[1:a][2:a]amix=inputs=2:duration=longest[aout]',
                    '-map', vid_map, '-map', '[aout]']
        elif vf_str:
            cmd += ['-vf', vf_str]

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

    def _last_log_line(self, default: str) -> str:
        try:
            log = open('/tmp/p2record_ffmpeg.log').read()
            lines = [l for l in log.splitlines() if l.strip()]
            return lines[-1] if lines else default
        except Exception:
            return default

    def _cleanup_failed_launch(self) -> None:
        """Kill any half-started processes and release the log file."""
        for proc in (self._gst_process, self._process):
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
        self._gst_process = None
        self._process = None
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
        if self._portal_stop_event:
            self._portal_stop_event.set()
            self._portal_stop_event = None

    def _launch(self, cmd: List[str], label: str, emit_on_fail: bool = False) -> bool:
        # Runs in a background thread — use GLib.idle_add for GTK/GLib calls.
        print(f'[Recorder] Starting ({label}):')
        print(' ', ' '.join(cmd))
        try:
            log_path = '/tmp/p2record_ffmpeg.log'
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
            self._log_file = open(log_path, 'w')
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=self._log_file,
                stderr=self._log_file,
            )
        except FileNotFoundError:
            self._cleanup_failed_launch()
            GLib.idle_add(lambda: self._emit_error('FFmpeg nicht gefunden — bitte das Paket "ffmpeg" installieren.') or False)
            return False

        import time
        time.sleep(0.8)
        if self._process.poll() is not None:
            msg = self._last_log_line('FFmpeg-Start fehlgeschlagen')
            print(f'[Recorder] FFmpeg failed: {msg}')
            if label != 'Software':
                print(f'[Recorder] {label} fehlgeschlagen, versuche Software-Encoding…')
            if emit_on_fail:
                GLib.idle_add(lambda m=msg: self._emit_error(m) or False)
            self._cleanup_failed_launch()
            return False

        self._using_vaapi = label == 'VAAPI'
        self._is_recording = True
        enc = label if label != 'Software' else 'Software (libx264, 30fps)'
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
            # Kill the surviving half of the pipeline so it can't linger
            for proc in (self._gst_process, self._process):
                if proc and proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
            self._is_recording = False
            self._process = None
            self._gst_process = None
            self._cleanup_timer_id = None
            self._monitor_timer_id = None
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
                self._log_file = None
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
                self._restart_timer_id = GLib.timeout_add_seconds(3, self._auto_restart)
            else:
                self._crash_count = 0
                last = self._last_log_line('')
                msg = f'FFmpeg: {last}' if last else 'Aufnahme unterbrochen – zu viele Abstürze'
                print(f'[Recorder] Zu viele Abstürze — gebe auf: {msg}')
                self._emit_error(msg)
            return False
        return True

    def _auto_restart(self) -> bool:
        self._restart_timer_id = None
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
