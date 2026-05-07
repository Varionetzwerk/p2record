import sys
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from core.settings import Settings
from core.recorder import Recorder
from core.hotkeys import HotkeyManager
from core.game_detector import GameDetector
from core.clip_manager import ClipManager
import core.i18n as i18n
from core.i18n import t


class P2RecordApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='de.p2record.app',
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

        self.settings = Settings()
        i18n.set_language(self.settings.get('language', 'de'))
        self.recorder = Recorder(self.settings)
        self.hotkeys = HotkeyManager()
        self.clip_manager = ClipManager(self.settings)
        self.current_game: str | None = None

        self.game_detector = GameDetector(self._on_game_changed)

        self.connect('activate', self._on_activate)
        self.connect('shutdown', self._on_shutdown)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _on_activate(self, app):
        from ui.main_window import MainWindow

        # Apply dark gaming theme
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        self._window = MainWindow(app)
        self._load_css()
        self._window.present()

        # Wire recorder callbacks
        self.recorder.on_state_changed = self._window.on_recording_state_changed
        self.recorder.on_error = self._window.on_recorder_error
        self.recorder.on_buffer_fill = self._window.on_buffer_fill_changed

        # Start subsystems
        self.game_detector.start()
        self.hotkeys.init()
        self._register_hotkeys()

        # Buffer fill ticker (1 second)
        GLib.timeout_add_seconds(1, self._tick_buffer)

        if self.settings.get('auto_record'):
            self.recorder.start()

    def _on_shutdown(self, app):
        self.recorder.stop()
        self.hotkeys.destroy()
        self.game_detector.stop()

    # ── Hotkeys ────────────────────────────────────────────────────────────────

    def _register_hotkeys(self) -> None:
        self.hotkeys.unregister_all()

        save_key = self.settings.get('save_hotkey', '')
        if save_key:
            self.hotkeys.register(save_key, self._on_save_hotkey)

        toggle_key = self.settings.get('toggle_hotkey', '')
        if toggle_key:
            self.hotkeys.register(toggle_key, self._on_toggle_hotkey)

    def reregister_hotkeys(self) -> None:
        self._register_hotkeys()

    def _on_save_hotkey(self) -> None:
        clip_duration = self.settings.get('clip_duration', 60)
        self._do_save_clip(clip_duration)

    def _on_toggle_hotkey(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
        else:
            self.recorder.start()

    def _do_save_clip(self, clip_duration: int) -> None:
        import threading
        def _save():
            path = self.recorder.save_clip(clip_duration, self.current_game)
            GLib.idle_add(self._on_clip_saved, path)
        threading.Thread(target=_save, daemon=True).start()

    def _on_clip_saved(self, path: str | None) -> None:
        if path and hasattr(self, '_window'):
            self._window.on_clip_saved(path)
            if self.settings.get('show_notifications'):
                self._notify(t('app.clip_saved_title'), Path(path).name)
        elif path is None and hasattr(self, '_window'):
            self._window.on_recorder_error(t('app.no_clip'))

    # ── Misc callbacks ─────────────────────────────────────────────────────────

    def _on_game_changed(self, game: str | None) -> None:
        self.current_game = game
        if hasattr(self, '_window'):
            self._window.on_game_changed(game)

    def _tick_buffer(self) -> bool:
        if hasattr(self, '_window'):
            fill = self.recorder.get_buffer_fill()
            self._window.on_buffer_fill_changed(fill)
        return True

    def _notify(self, title: str, body: str) -> None:
        n = Gio.Notification.new(title)
        n.set_body(body)
        self.send_notification(None, n)

    def _load_css(self) -> None:
        css_path = Path(__file__).parent.parent / 'resources' / 'style.css'
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_save_clip_external(self, clip_duration: int) -> None:
        self._do_save_clip(clip_duration)
