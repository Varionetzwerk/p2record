import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from core.i18n import t


class HelpPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._app = app
        self._build()

    def _build(self) -> None:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_start(24)
        header.set_margin_end(24)
        header.set_margin_top(20)
        header.set_margin_bottom(16)

        title = Gtk.Label(label=t('help.title'))
        title.add_css_class('page-title')
        title.set_halign(Gtk.Align.START)
        header.append(title)

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

        sections = [
            ('help.s1.title', 'help.s1.body'),
            ('help.s2.title', 'help.s2.body'),
            ('help.s3.title', 'help.s3.body'),
            ('help.s4.title', 'help.s4.body'),
            ('help.s5.title', 'help.s5.body'),
            ('help.s6.title', 'help.s6.body'),
            ('help.s7.title', 'help.s7.body'),
        ]

        for title_key, body_key in sections:
            content.append(self._section(t(title_key), t(body_key)))

    def _section(self, heading: str, body: str) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class('card')

        lbl_h = Gtk.Label(label=heading)
        lbl_h.add_css_class('section-title')
        lbl_h.set_halign(Gtk.Align.START)
        card.append(lbl_h)

        lbl_b = Gtk.Label(label=body)
        lbl_b.add_css_class('row-hint')
        lbl_b.set_halign(Gtk.Align.START)
        lbl_b.set_wrap(True)
        lbl_b.set_xalign(0)
        card.append(lbl_b)

        return card
