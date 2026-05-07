from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from ui.pages.dashboard import DashboardPage
from ui.pages.help_page import HelpPage
from ui.pages.library import LibraryPage
from ui.pages.settings_page import SettingsPage
from core.i18n import t


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='P2-Record')
        self.set_default_size(960, 660)
        self.set_size_request(820, 540)

        self._app = app

        # ── Outer wrapper (header bar + content) ───────────────────────────────
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(outer)

        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=t('app.title')))
        header.add_css_class('flat')
        outer.append(header)

        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # ── Layout: sidebar + stack ────────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.set_vexpand(True)
        outer.append(root)

        # Stack + pages must exist before sidebar (nav buttons fire on set_active)
        self._stack = Gtk.Stack()
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)

        # ── Pages (added before sidebar so navigation works immediately) ───────
        self._dashboard = DashboardPage(app)
        self._library = LibraryPage(app)
        self._settings_page = SettingsPage(app)
        self._help_page = HelpPage(app)

        self._stack.add_named(self._dashboard, 'dashboard')
        self._stack.add_named(self._library, 'library')
        self._stack.add_named(self._settings_page, 'settings')
        self._stack.add_named(self._help_page, 'help')

        sidebar = self._build_sidebar()
        root.append(sidebar)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        root.append(sep)

        root.append(self._stack)

    # ── Sidebar ────────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(200, -1)
        box.add_css_class('sidebar')

        # App title
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header.set_margin_start(20)
        header.set_margin_top(20)
        header.set_margin_bottom(8)
        title = Gtk.Label(label=t('app.title'))
        title.add_css_class('app-title')
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label=t('app.subtitle'))
        subtitle.add_css_class('app-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        header.append(title)
        header.append(subtitle)
        box.append(header)

        sep = Gtk.Separator()
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        box.append(sep)

        # Nav buttons
        nav_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        nav_box.set_margin_start(8)
        nav_box.set_margin_end(8)
        nav_box.set_spacing(4)

        self._nav_btns: dict[str, Gtk.ToggleButton] = {}

        pages = [
            ('dashboard', 'go-home-symbolic',            t('nav.dashboard')),
            ('library',   'folder-videos-symbolic',      t('nav.library')),
            ('settings',  'preferences-system-symbolic', t('nav.settings')),
            ('help',      'help-about-symbolic',         t('nav.help')),
        ]

        first_btn = None
        for name, icon, label in pages:
            btn = self._make_nav_btn(name, icon, label)
            if first_btn is None:
                first_btn = btn
                btn.set_active(True)
            nav_box.append(btn)
            self._nav_btns[name] = btn

        box.append(nav_box)

        # Recording indicator at bottom
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        box.append(spacer)

        self._rec_indicator = Gtk.Label(label=t('rec.off'))
        self._rec_indicator.add_css_class('rec-indicator')
        self._rec_indicator.add_css_class('rec-off')
        self._rec_indicator.set_margin_start(20)
        self._rec_indicator.set_margin_bottom(20)
        self._rec_indicator.set_halign(Gtk.Align.START)
        box.append(self._rec_indicator)

        return box

    def _make_nav_btn(self, page: str, icon: str, label: str) -> Gtk.ToggleButton:
        btn = Gtk.ToggleButton()
        btn.add_css_class('nav-btn')
        btn.set_hexpand(True)
        btn.set_halign(Gtk.Align.FILL)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(8)
        content.set_margin_bottom(8)

        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(16)
        content.append(img)

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        content.append(lbl)

        btn.set_child(content)
        btn.connect('toggled', self._on_nav_toggled, page)
        return btn

    def _on_nav_toggled(self, btn: Gtk.ToggleButton, page: str) -> None:
        if not btn.get_active():
            return
        # Deactivate other buttons
        for name, other in self._nav_btns.items():
            if name != page and other.get_active():
                other.handler_block_by_func(self._on_nav_toggled)
                other.set_active(False)
                other.handler_unblock_by_func(self._on_nav_toggled)

        self._stack.set_visible_child_name(page)
        if page == 'library':
            self._library.refresh()

    # ── Callbacks from App ─────────────────────────────────────────────────────

    def on_recording_state_changed(self, is_recording: bool) -> None:
        self._dashboard.set_recording(is_recording)
        if is_recording:
            self._rec_indicator.set_text(t('rec.on'))
            self._rec_indicator.remove_css_class('rec-off')
            self._rec_indicator.add_css_class('rec-on')
        else:
            self._rec_indicator.set_text(t('rec.off'))
            self._rec_indicator.remove_css_class('rec-on')
            self._rec_indicator.add_css_class('rec-off')

    def on_recorder_error(self, msg: str) -> None:
        self._dashboard.set_error(msg)

    def on_buffer_fill_changed(self, fill: float) -> None:
        self._dashboard.set_buffer_fill(fill)

    def on_game_changed(self, game: Optional[str]) -> None:
        self._dashboard.set_game(game)

    def on_clip_saved(self, path: str) -> None:
        self._dashboard.flash_saved(path)
        self._play_chime()

    def _play_chime(self) -> None:
        # Simple system bell as fallback — GTK4 has no Web Audio API
        # Real chime via paplay if available
        import subprocess, shutil
        if shutil.which('paplay'):
            import threading
            def _play():
                try:
                    subprocess.run(['paplay', '/usr/share/sounds/freedesktop/stereo/complete.oga'],
                                   timeout=3, capture_output=True)
                except Exception:
                    pass
            threading.Thread(target=_play, daemon=True).start()
