import subprocess
from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GLib, Gtk

from core.i18n import t

# GTK uses this sentinel when no item is selected (0xFFFFFFFF).
# It can fire during widget realization before the real selection is set,
# which would corrupt the change-guard and trigger spurious callbacks.
_INVALID_POS = 4294967295


class HotkeyEntry(Gtk.Entry):
    """Captures a single keypress and stores it as e.g. 'F9' or 'Control+F9'."""

    def __init__(self, value: str = ''):
        super().__init__()
        self.set_editable(False)
        self.set_can_focus(True)
        self.set_width_chars(14)
        self.add_css_class('hotkey-entry')
        self._capturing = False
        self._value = value
        self._update_display()

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect('key-pressed', self._on_key_pressed)
        self.add_controller(key_ctrl)

        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect('enter', self._on_focus_in)
        focus_ctrl.connect('leave', self._on_focus_out)
        self.add_controller(focus_ctrl)

    def get_hotkey(self) -> str:
        return self._value

    def set_hotkey(self, value: str) -> None:
        self._value = value
        self._update_display()

    def _update_display(self) -> None:
        if self._capturing:
            self.set_text(t('settings.hotkeys.capturing'))
        else:
            self.set_text(self._value or '—')

    def _on_focus_in(self, ctrl) -> None:
        self._capturing = True
        self._update_display()

    def _on_focus_out(self, ctrl) -> None:
        self._capturing = False
        self._update_display()

    def _on_key_pressed(self, ctrl, keyval, keycode, state) -> bool:
        if not self._capturing:
            return False

        # BackSpace/Delete clears the hotkey entirely
        if keyval in (Gdk.KEY_BackSpace, Gdk.KEY_Delete):
            self._value = ''
            self._capturing = False
            self._update_display()
            self.emit('activate')
            return True

        ignored = {
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
            Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
            Gdk.KEY_Super_L, Gdk.KEY_Super_R,
            Gdk.KEY_Caps_Lock, Gdk.KEY_Tab, Gdk.KEY_Escape,
        }
        if keyval in ignored:
            return True

        parts = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            parts.append('Control')
        if state & Gdk.ModifierType.ALT_MASK:
            parts.append('Alt')
        if state & Gdk.ModifierType.SHIFT_MASK:
            parts.append('Shift')
        if state & Gdk.ModifierType.SUPER_MASK:
            parts.append('Super')

        key_name = Gdk.keyval_name(keyval) or ''
        if len(key_name) == 1:
            key_name = key_name.upper()
        parts.append(key_name)

        self._value = '+'.join(parts)
        self._capturing = False
        self._update_display()
        self.emit('activate')
        return True


class SettingsPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._app = app
        self._saved_timer: Optional[int] = None
        self._build()

    def _build(self) -> None:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_start(24)
        header.set_margin_end(24)
        header.set_margin_top(20)
        header.set_margin_bottom(16)

        title = Gtk.Label(label=t('settings.title'))
        title.add_css_class('page-title')
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)

        self._saved_lbl = Gtk.Label(label=t('settings.saved'))
        self._saved_lbl.add_css_class('saved-badge')
        self._saved_lbl.set_visible(False)
        header.append(self._saved_lbl)

        self.append(header)
        self.append(Gtk.Separator())

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

        content.append(self._build_monitor_section())
        content.append(self._build_hotkeys_section())
        content.append(self._build_recording_section())
        content.append(self._build_output_section())
        content.append(self._build_behaviour_section())
        content.append(self._build_info_section())

    # ── Section builders ───────────────────────────────────────────────────────

    def _build_monitor_section(self) -> Gtk.Widget:
        from core.screen_picker import list_monitors
        box = self._section(t('settings.monitor.section'))
        monitors = list_monitors()

        if not monitors:
            box.append(self._info_box(t('settings.monitor.no_monitors'), 'status-warn'))
            return box

        import os
        if os.environ.get('WAYLAND_DISPLAY'):
            box.append(self._info_box(t('settings.monitor.wayland_info'), 'status-ok'))

        s = self._app.settings
        current = s.get('capture_monitor', '')

        options = [(m.name, m.label()) for m in monitors]
        idx = 0
        for i, (name, _) in enumerate(options):
            if name == current:
                idx = i
                break
        if not current:
            for i, m in enumerate(monitors):
                if m.primary:
                    idx = i
                    break

        self._monitor_options = options

        strings = Gtk.StringList()
        for _, label in options:
            strings.append(label)

        dd = Gtk.DropDown(model=strings)
        dd.set_selected(idx)
        dd.add_css_class('settings-dropdown')

        _last_idx = [idx]

        def on_monitor_changed(obj, _pspec):
            sel = obj.get_selected()
            # Ignore GTK's INVALID_LIST_POSITION sentinel fired during realization
            if sel == _INVALID_POS or sel == _last_idx[0]:
                return
            _last_idx[0] = sel
            if 0 <= sel < len(options):
                name = options[sel][0]
                self._set('capture_monitor', name)
                import os
                if os.environ.get('WAYLAND_DISPLAY'):
                    # The portal restores the previous screen silently via the
                    # saved token — delete it so the picker dialog reappears.
                    from core.portal import clear_restore_token
                    clear_restore_token()
                if self._app.recorder.is_recording:
                    self._app.recorder.stop()
                    self._app.recorder.start()

        dd.connect('notify::selected', on_monitor_changed)

        mon = monitors[idx]
        hint = f'{mon.width}×{mon.height} px'
        box.append(self._row(t('settings.monitor.label'), hint, dd))
        return box

    def _build_hotkeys_section(self) -> Gtk.Widget:
        box = self._section(t('settings.hotkeys.section'))

        if self._app.hotkeys.using_evdev:
            box.append(self._info_box(t('settings.hotkeys.evdev_ok'), css='status-ok'))
        else:
            box.append(self._info_box(t('settings.hotkeys.evdev_warn'), css='status-warn'))

        s = self._app.settings
        self._save_hotkey_entry = HotkeyEntry(s.get('save_hotkey', 'F9'))
        self._save_hotkey_entry.connect('activate', self._on_save_hotkey_changed)
        box.append(self._row(t('settings.hotkeys.save'), t('settings.hotkeys.save_hint'), self._save_hotkey_entry))

        self._toggle_hotkey_entry = HotkeyEntry(s.get('toggle_hotkey', ''))
        self._toggle_hotkey_entry.connect('activate', self._on_toggle_hotkey_changed)
        box.append(self._row(t('settings.hotkeys.toggle'), t('settings.hotkeys.toggle_hint'), self._toggle_hotkey_entry))

        return box

    def _build_recording_section(self) -> Gtk.Widget:
        box = self._section(t('settings.rec.section'))
        s = self._app.settings

        self._buf_adj = Gtk.Adjustment(value=s.get('buffer_duration', 120),
                                       lower=30, upper=600, step_increment=30)
        self._buf_adj.connect('value-changed', lambda a: self._set('buffer_duration', int(a.get_value())))
        buf_scale = self._scale(self._buf_adj)
        self._buf_lbl = Gtk.Label(label=self._fmt(s.get('buffer_duration', 120)))
        self._buf_lbl.add_css_class('row-value')
        self._buf_lbl.set_width_chars(6)
        self._buf_adj.connect('value-changed', lambda a: self._buf_lbl.set_text(self._fmt(int(a.get_value()))))
        buf_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buf_row.append(buf_scale)
        buf_row.append(self._buf_lbl)
        box.append(self._row(t('settings.rec.buffer'), t('settings.rec.buffer_hint'), buf_row))

        self._clip_adj = Gtk.Adjustment(value=s.get('clip_duration', 60),
                                        lower=15, upper=s.get('buffer_duration', 120), step_increment=15)
        self._clip_adj.connect('value-changed', lambda a: self._set('clip_duration', int(a.get_value())))
        clip_scale = self._scale(self._clip_adj)
        self._clip_lbl = Gtk.Label(label=self._fmt(s.get('clip_duration', 60)))
        self._clip_lbl.add_css_class('row-value')
        self._clip_lbl.set_width_chars(6)
        self._clip_adj.connect('value-changed', lambda a: self._clip_lbl.set_text(self._fmt(int(a.get_value()))))
        clip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        clip_row.append(clip_scale)
        clip_row.append(self._clip_lbl)
        box.append(self._row(t('settings.rec.clip'), t('settings.rec.clip_hint'), clip_row))

        # Clip length can never exceed the ring buffer — keep the upper bound in sync
        def _sync_clip_upper(adj):
            upper = int(adj.get_value())
            self._clip_adj.set_upper(upper)
            if self._clip_adj.get_value() > upper:
                self._clip_adj.set_value(upper)
        self._buf_adj.connect('value-changed', _sync_clip_upper)
        _sync_clip_upper(self._buf_adj)

        quality_combo = self._combo(
            [('low',    t('settings.rec.quality_low')),
             ('medium', t('settings.rec.quality_medium')),
             ('high',   t('settings.rec.quality_high')),
             ('ultra',  t('settings.rec.quality_ultra'))],
            s.get('quality', 'high'),
            lambda v: self._set('quality', v),
        )
        box.append(self._row(t('settings.rec.quality'), t('settings.rec.quality_hint'), quality_combo))

        res_combo = self._combo(
            [('native', t('settings.rec.res_native')), ('1440p', '1440p'),
             ('1080p', '1080p'), ('720p', '720p')],
            s.get('resolution', 'native'),
            lambda v: self._set('resolution', v),
        )
        box.append(self._row(t('settings.rec.resolution'), t('settings.rec.resolution_hint'), res_combo))

        fps_combo = self._combo(
            [(60, '60 FPS'), (30, '30 FPS')],
            s.get('fps', 60),
            lambda v: self._set('fps', int(v)),
        )
        box.append(self._row(t('settings.rec.fps'), '', fps_combo))

        audio_combo = self._combo(
            [('none',    t('settings.rec.audio_none')),
             ('desktop', t('settings.rec.audio_desktop')),
             ('mic',     t('settings.rec.audio_mic')),
             ('both',    t('settings.rec.audio_both'))],
            s.get('audio_source', 'desktop'),
            lambda v: self._set('audio_source', v),
        )
        box.append(self._row(t('settings.rec.audio'), t('settings.rec.audio_hint'), audio_combo))

        return box

    def _build_output_section(self) -> Gtk.Widget:
        box = self._section(t('settings.output.section'))
        s = self._app.settings

        path_btn = Gtk.Button(label=t('settings.output.change'))
        path_btn.add_css_class('btn-secondary')
        path_btn.connect('clicked', self._on_select_dir)

        box.append(self._row(t('settings.output.folder'), s.get('output_path', ''), path_btn))
        return box

    def _build_behaviour_section(self) -> Gtk.Widget:
        box = self._section(t('settings.behaviour.section'))
        s = self._app.settings

        box.append(self._row(
            t('settings.behaviour.auto_record'),
            t('settings.behaviour.auto_record_hint'),
            self._switch(s.get('auto_record', True), lambda v: self._set('auto_record', v)),
        ))
        box.append(self._row(
            t('settings.behaviour.notifications'),
            t('settings.behaviour.notifications_hint'),
            self._switch(s.get('show_notifications', True), lambda v: self._set('show_notifications', v)),
        ))

        lang_combo = self._combo(
            [('de', t('settings.behaviour.lang_de')),
             ('en', t('settings.behaviour.lang_en'))],
            s.get('language', 'de'),
            lambda v: self._set('language', v),
        )
        box.append(self._row(
            t('settings.behaviour.language'),
            t('settings.behaviour.language_hint'),
            lang_combo,
        ))

        return box

    def _build_info_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.add_css_class('info-box')

        icon = Gtk.Image.new_from_icon_name('dialog-information-symbolic')
        icon.set_pixel_size(14)
        icon.set_valign(Gtk.Align.START)
        box.append(icon)

        lbl = Gtk.Label()
        lbl.set_markup(t('settings.info'))
        lbl.add_css_class('info-text')
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        box.append(lbl)

        return box

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _section(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class('card')

        lbl = Gtk.Label(label=title)
        lbl.add_css_class('section-title')
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_bottom(8)
        box.append(lbl)

        return box

    def _row(self, label: str, hint: str, widget: Gtk.Widget) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.add_css_class('settings-row')

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)

        lbl = Gtk.Label(label=label)
        lbl.add_css_class('row-label')
        lbl.set_halign(Gtk.Align.START)
        left.append(lbl)

        if hint:
            hint_lbl = Gtk.Label(label=hint)
            hint_lbl.add_css_class('row-hint')
            hint_lbl.set_halign(Gtk.Align.START)
            hint_lbl.set_ellipsize(3)  # END
            left.append(hint_lbl)

        row.append(left)

        right = Gtk.Box()
        right.set_valign(Gtk.Align.CENTER)
        right.append(widget)
        row.append(right)

        return row

    def _switch(self, value: bool, on_change) -> Gtk.Switch:
        sw = Gtk.Switch()
        sw.set_active(value)
        sw.set_valign(Gtk.Align.CENTER)
        sw.connect('state-set', lambda s, v: on_change(v))
        return sw

    def _combo(self, options: list, current, on_change) -> Gtk.DropDown:
        strings = Gtk.StringList()
        idx = 0
        for i, (val, label) in enumerate(options):
            strings.append(label)
            if val == current:
                idx = i

        dd = Gtk.DropDown(model=strings)
        dd.set_selected(idx)
        dd.add_css_class('settings-dropdown')

        _last = [idx]

        def on_notify(obj, _pspec):
            sel = obj.get_selected()
            if sel == _INVALID_POS or sel == _last[0]:
                return
            _last[0] = sel
            if 0 <= sel < len(options):
                on_change(options[sel][0])

        dd.connect('notify::selected', on_notify)
        return dd

    def _scale(self, adj: Gtk.Adjustment) -> Gtk.Scale:
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_draw_value(False)
        scale.set_size_request(160, -1)
        return scale

    def _info_box(self, text: str, css: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.add_css_class(css)
        box.set_margin_bottom(8)

        lbl = Gtk.Label(label=text)
        lbl.set_wrap(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.add_css_class('info-text')
        box.append(lbl)
        return box

    def _fmt(self, s: int) -> str:
        from core.i18n import t as _t
        return f'{s} {_t("dash.sec")}' if s < 60 else f'{s // 60} {_t("dash.min")}'

    # ── Setters ────────────────────────────────────────────────────────────────

    def _set(self, key: str, value) -> None:
        self._app.settings.set(key, value)
        self._app.reregister_hotkeys()
        self._flash_saved()

    def _flash_saved(self) -> None:
        self._saved_lbl.set_visible(True)
        if self._saved_timer:
            GLib.source_remove(self._saved_timer)
        self._saved_timer = GLib.timeout_add(1800, self._hide_saved)

    def _hide_saved(self) -> bool:
        self._saved_lbl.set_visible(False)
        self._saved_timer = None
        return False

    def _on_save_hotkey_changed(self, entry) -> None:
        self._set('save_hotkey', entry.get_hotkey())

    def _on_toggle_hotkey_changed(self, entry) -> None:
        self._set('toggle_hotkey', entry.get_hotkey())

    def _on_select_dir(self, btn) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title(t('settings.output.dialog'))
        dialog.select_folder(self.get_root(), None, self._on_dir_chosen, None)

    def _on_dir_chosen(self, dialog, result, data) -> None:
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self._set('output_path', path)
        except Exception:
            pass
