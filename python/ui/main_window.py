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
from core.updater import check_for_update, CURRENT_VERSION


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

        # ── Update banner ──────────────────────────────────────────────────────
        self._update_banner = Adw.Banner(
            title='',
            button_label=t('update.btn'),
            revealed=False,
        )
        self._update_banner.connect('button-clicked', self._on_update_clicked)
        outer.append(self._update_banner)

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

        # ── Check for updates (after UI is built) ──────────────────────────────
        GLib.timeout_add_seconds(3, self._start_update_check)

    def _start_update_check(self) -> bool:
        check_for_update(self._on_update_result)
        return False  # run once

    def _on_update_result(self, latest: Optional[str]) -> None:
        if latest is None:
            GLib.idle_add(self._set_version_status, 'error', '')
        elif latest == '':
            GLib.idle_add(self._set_version_status, 'current', '')
        else:
            GLib.idle_add(self._show_update_banner, latest)
            GLib.idle_add(self._set_version_status, 'update', latest)

    def _set_version_status(self, state: str, version: str) -> bool:
        from core.updater import CURRENT_VERSION
        if state == 'current':
            self._version_label.set_text(t('update.uptodate', version=CURRENT_VERSION))
        elif state == 'update':
            self._version_label.set_text(t('update.newer', version=version))
        else:
            self._version_label.set_text(t('update.error'))
        return False

    def _show_update_banner(self, version: str) -> bool:
        self._update_banner.set_title(t('update.available', version=version))
        self._update_banner.set_revealed(True)
        self._latest_version = version
        return False

    def _on_update_clicked(self, _banner) -> None:
        dialog = Adw.AlertDialog(
            heading=t('update.dialog.title'),
            body=t('update.dialog.body'),
        )
        # Command box
        cmd_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cmd_row.set_margin_top(8)
        frame = Gtk.Frame()
        frame.add_css_class('card')
        cmd_label = Gtk.Label(label='yay -S p2record-git')
        cmd_label.add_css_class('monospace')
        cmd_label.set_margin_top(12)
        cmd_label.set_margin_bottom(12)
        cmd_label.set_margin_start(16)
        cmd_label.set_margin_end(16)
        cmd_label.set_selectable(True)
        frame.set_child(cmd_label)
        cmd_row.append(frame)
        dialog.set_extra_child(cmd_row)
        dialog.add_response('close', t('update.dialog.close'))
        dialog.set_default_response('close')
        dialog.present(self)

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
        self._rec_indicator.set_margin_bottom(4)
        self._rec_indicator.set_halign(Gtk.Align.START)
        box.append(self._rec_indicator)

        self._version_label = Gtk.Label(label=t('update.checking'))
        self._version_label.add_css_class('dim-label')
        self._version_label.set_margin_start(20)
        self._version_label.set_margin_bottom(16)
        self._version_label.set_halign(Gtk.Align.START)
        box.append(self._version_label)

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
            # Clicking the active button must not deselect it — re-activate
            if self._stack.get_visible_child_name() == page:
                btn.handler_block_by_func(self._on_nav_toggled)
                btn.set_active(True)
                btn.handler_unblock_by_func(self._on_nav_toggled)
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
            self._dashboard.clear_error()
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

    def _play_chime(self) -> None:
        import subprocess, shutil, threading
        from pathlib import Path as _P

        _SOUNDS = [
            '/usr/share/sounds/freedesktop/stereo/complete.oga',
            '/usr/share/sounds/freedesktop/stereo/bell.oga',
            '/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga',
            '/usr/share/sounds/gnome/default/alerts/glass.ogg',
        ]

        def _play():
            for player in ('paplay', 'pw-play', 'aplay'):
                if not shutil.which(player):
                    continue
                for sf in _SOUNDS:
                    if not _P(sf).exists():
                        continue
                    try:
                        if subprocess.run([player, sf], timeout=3,
                                          capture_output=True).returncode == 0:
                            return
                    except Exception:
                        continue
            # Last resort: Gdk system bell
            try:
                from gi.repository import Gdk as _Gdk
                display = _Gdk.Display.get_default()
                if display:
                    GLib.idle_add(display.beep)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()
