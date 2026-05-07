import subprocess
import threading
from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import GdkPixbuf, GLib, Gtk

from core.clip_manager import Clip
from core.i18n import t


class LibraryPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._app = app
        self._build()

    def _build(self) -> None:
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_start(24)
        header.set_margin_end(24)
        header.set_margin_top(20)
        header.set_margin_bottom(16)

        title = Gtk.Label(label=t('library.title'))
        title.add_css_class('page-title')
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name('view-refresh-symbolic')
        refresh_btn.add_css_class('btn-secondary')
        refresh_btn.connect('clicked', lambda _: self.refresh())
        header.append(refresh_btn)

        self.append(header)
        self.append(Gtk.Separator())

        # Empty state
        self._empty_label = Gtk.Label(label=t('library.empty'))
        self._empty_label.add_css_class('empty-label')
        self._empty_label.set_vexpand(True)
        self._empty_label.set_valign(Gtk.Align.CENTER)
        self.append(self._empty_label)

        # Clip list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class('clip-list')
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self._list_box)

    def refresh(self) -> None:
        clips = self._app.clip_manager.list_clips()

        # Clear list
        while True:
            row = self._list_box.get_first_child()
            if row is None:
                break
            self._list_box.remove(row)

        if not clips:
            self._empty_label.set_visible(True)
            self._list_box.set_visible(False)
            return

        self._empty_label.set_visible(False)
        self._list_box.set_visible(True)

        for clip in clips:
            row = self._make_clip_row(clip)
            self._list_box.append(row)

    def _make_clip_row(self, clip: Clip) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_top(10)
        row.set_margin_bottom(10)
        row.add_css_class('clip-row')

        # Thumbnail
        thumb = Gtk.Image()
        thumb.set_pixel_size(80)
        thumb.set_size_request(112, 63)
        thumb.add_css_class('clip-thumb')
        if clip.thumbnail_path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(clip.thumbnail_path, 112, 63, True)
                thumb.set_from_pixbuf(pb)
            except Exception:
                thumb.set_from_icon_name('video-x-generic-symbolic')
        else:
            thumb.set_from_icon_name('video-x-generic-symbolic')
            # Generate thumb async
            threading.Thread(
                target=self._gen_thumb, args=(clip.file_path, thumb), daemon=True
            ).start()
        row.append(thumb)

        # Clip info
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)

        name_lbl = Gtk.Label(label=clip.game_name)
        name_lbl.add_css_class('clip-game')
        name_lbl.set_halign(Gtk.Align.START)
        info.append(name_lbl)

        meta = f'{clip.created_at}  ·  {self._fmt_dur(clip.duration)}  ·  {self._fmt_size(clip.size)}'
        meta_lbl = Gtk.Label(label=meta)
        meta_lbl.add_css_class('clip-meta')
        meta_lbl.set_halign(Gtk.Align.START)
        info.append(meta_lbl)
        row.append(info)

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_valign(Gtk.Align.CENTER)

        open_btn = Gtk.Button()
        open_btn.set_icon_name('folder-open-symbolic')
        open_btn.add_css_class('btn-secondary')
        open_btn.set_tooltip_text(t('library.open_folder'))
        open_btn.connect('clicked', lambda _, p=clip.file_path: self._app.clip_manager.open_folder(p))
        actions.append(open_btn)

        play_btn = Gtk.Button()
        play_btn.set_icon_name('media-playback-start-symbolic')
        play_btn.add_css_class('btn-secondary')
        play_btn.set_tooltip_text(t('library.play'))
        play_btn.connect('clicked', lambda _, p=clip.file_path: self._play(p))
        actions.append(play_btn)

        del_btn = Gtk.Button()
        del_btn.set_icon_name('user-trash-symbolic')
        del_btn.add_css_class('btn-danger-small')
        del_btn.set_tooltip_text(t('library.delete'))
        del_btn.connect('clicked', lambda _, c=clip, r=row: self._delete(c, r))
        actions.append(del_btn)

        row.append(actions)
        return row

    def _gen_thumb(self, file_path: str, img_widget: Gtk.Image) -> None:
        path = self._app.clip_manager.generate_thumbnail(file_path)
        if path:
            GLib.idle_add(self._set_thumb, img_widget, path)

    def _set_thumb(self, img: Gtk.Image, path: str) -> None:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 112, 63, True)
            img.set_from_pixbuf(pb)
        except Exception:
            pass

    def _play(self, file_path: str) -> None:
        subprocess.Popen(['xdg-open', file_path])

    def _delete(self, clip: Clip, row: Gtk.Widget) -> None:
        self._app.clip_manager.delete_clip(clip.file_path)
        # ListBox wraps children in ListBoxRow — remove the parent row
        list_row = row.get_parent()
        if list_row:
            self._list_box.remove(list_row)
        if not self._list_box.get_first_child():
            self._empty_label.set_visible(True)
            self._list_box.set_visible(False)

    def _fmt_dur(self, secs: float) -> str:
        s = int(secs)
        return f'{s // 60}:{s % 60:02d}'

    def _fmt_size(self, b: int) -> str:
        if b >= 1_000_000_000:
            return f'{b/1e9:.1f} GB'
        if b >= 1_000_000:
            return f'{b/1e6:.0f} MB'
        return f'{b/1e3:.0f} KB'
