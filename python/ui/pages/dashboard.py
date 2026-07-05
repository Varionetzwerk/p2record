from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from core.i18n import t


class DashboardPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._app = app
        self._saved_timer_id: Optional[int] = None
        self._build()
        # Keep the hotkey/clip-length hint in sync with the settings page
        app.settings.connect_changed(self._on_setting_changed)

    def _build(self) -> None:
        # ── Header ─────────────────────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_start(24)
        header.set_margin_end(24)
        header.set_margin_top(20)
        header.set_margin_bottom(16)

        title = Gtk.Label(label=t('dash.title'))
        title.add_css_class('page-title')
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)

        self._saved_badge = Gtk.Label(label=t('dash.saved'))
        self._saved_badge.add_css_class('saved-badge')
        self._saved_badge.set_visible(False)
        header.append(self._saved_badge)

        self.append(header)
        self.append(Gtk.Separator())

        # ── Content ────────────────────────────────────────────────────────────
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        scroll.set_child(content)

        content.append(self._build_status_card())
        content.append(self._build_actions_card())

        self._error_label = Gtk.Label()
        self._error_label.add_css_class('error-label')
        self._error_label.set_visible(False)
        self._error_label.set_wrap(True)
        content.append(self._error_label)

    def _build_status_card(self) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        card.add_css_class('card')

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self._dot = Gtk.Label(label='●')
        self._dot.add_css_class('status-dot')
        self._dot.add_css_class('dot-off')
        status_row.append(self._dot)

        status_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._status_label = Gtk.Label(label=t('dash.not_recording'))
        self._status_label.add_css_class('status-label')
        self._status_label.set_halign(Gtk.Align.START)
        status_col.append(self._status_label)

        self._game_label = Gtk.Label(label=t('dash.no_game'))
        self._game_label.add_css_class('game-label')
        self._game_label.set_halign(Gtk.Align.START)
        status_col.append(self._game_label)
        status_row.append(status_col)

        card.append(status_row)

        buf_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        buf_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        buf_lbl = Gtk.Label(label=t('dash.ring_buffer'))
        buf_lbl.add_css_class('row-label')
        buf_lbl.set_halign(Gtk.Align.START)
        buf_lbl.set_hexpand(True)
        buf_header.append(buf_lbl)

        self._buf_pct = Gtk.Label(label='0%')
        self._buf_pct.add_css_class('row-value')
        buf_header.append(self._buf_pct)
        buf_box.append(buf_header)

        self._progress = Gtk.ProgressBar()
        self._progress.add_css_class('buffer-progress')
        self._progress.set_fraction(0.0)
        buf_box.append(self._progress)

        card.append(buf_box)
        return card

    def _build_actions_card(self) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('card')

        label = Gtk.Label(label=t('dash.actions'))
        label.add_css_class('card-title')
        label.set_halign(Gtk.Align.START)
        card.append(label)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self._toggle_btn = Gtk.Button(label=t('dash.start'))
        self._toggle_btn.add_css_class('btn-primary')
        self._toggle_btn.set_hexpand(True)
        self._toggle_btn.connect('clicked', self._on_toggle)
        btn_row.append(self._toggle_btn)

        save_btn = Gtk.Button()
        save_btn.add_css_class('btn-accent')
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        save_icon = Gtk.Image.new_from_icon_name('document-save-symbolic')
        save_box.append(save_icon)
        save_box.append(Gtk.Label(label=t('dash.save_clip')))
        save_btn.set_child(save_box)
        save_btn.set_hexpand(True)
        save_btn.connect('clicked', self._on_save)
        btn_row.append(save_btn)

        card.append(btn_row)

        self._hint_lbl = Gtk.Label()
        self._hint_lbl.add_css_class('hint-label')
        self._hint_lbl.set_halign(Gtk.Align.START)
        self._refresh_hint()
        card.append(self._hint_lbl)

        return card

    def _refresh_hint(self) -> None:
        save_key = self._app.settings.get('save_hotkey', 'F9') or '—'
        dur = self._fmt(self._app.settings.get('clip_duration', 60))
        self._hint_lbl.set_text(t('dash.hotkey_hint', key=save_key, dur=dur))

    def _on_setting_changed(self, key: str, value) -> None:
        if key in ('save_hotkey', 'clip_duration'):
            self._refresh_hint()

    # ── Public state setters ───────────────────────────────────────────────────

    def set_recording(self, recording: bool) -> None:
        if recording:
            self._dot.remove_css_class('dot-off')
            self._dot.add_css_class('dot-on')
            self._status_label.set_text(t('dash.recording'))
            self._toggle_btn.set_label(t('dash.stop'))
            self._toggle_btn.remove_css_class('btn-primary')
            self._toggle_btn.add_css_class('btn-danger')
        else:
            self._dot.remove_css_class('dot-on')
            self._dot.add_css_class('dot-off')
            self._status_label.set_text(t('dash.not_recording'))
            self._toggle_btn.set_label(t('dash.start'))
            self._toggle_btn.remove_css_class('btn-danger')
            self._toggle_btn.add_css_class('btn-primary')
            self._progress.set_fraction(0.0)
            self._buf_pct.set_text('0%')

    def set_buffer_fill(self, fill: float) -> None:
        self._progress.set_fraction(min(fill, 1.0))
        self._buf_pct.set_text(f'{int(fill * 100)}%')

    def set_game(self, game: Optional[str]) -> None:
        self._game_label.set_text(game or t('dash.no_game'))

    def set_error(self, msg: str) -> None:
        if msg.endswith('…') or 'Neustart' in msg or 'restart' in msg.lower():
            self._error_label.remove_css_class('error-label')
            self._error_label.add_css_class('info-label')
            self._error_label.set_text(msg)
        else:
            self._error_label.remove_css_class('info-label')
            self._error_label.add_css_class('error-label')
            self._error_label.set_text(f'{t("dash.error_prefix")}{msg}')
        self._error_label.set_visible(True)

    def clear_error(self) -> None:
        self._error_label.set_visible(False)

    def flash_saved(self, path: str) -> None:
        self._error_label.set_visible(False)
        self._saved_badge.set_visible(True)
        if self._saved_timer_id:
            GLib.source_remove(self._saved_timer_id)
        self._saved_timer_id = GLib.timeout_add(2000, self._hide_saved)

    def _hide_saved(self) -> bool:
        self._saved_badge.set_visible(False)
        self._saved_timer_id = None
        return False

    # ── Button handlers ────────────────────────────────────────────────────────

    def _on_toggle(self, btn) -> None:
        if self._app.recorder.is_recording:
            self._app.recorder.stop()
        else:
            self._app.recorder.start()

    def _on_save(self, btn) -> None:
        clip_duration = self._app.settings.get('clip_duration', 60)
        self._app.do_save_clip_external(clip_duration)

    def _fmt(self, s: int) -> str:
        return f'{s} {t("dash.sec")}' if s < 60 else f'{s // 60} {t("dash.min")}'
