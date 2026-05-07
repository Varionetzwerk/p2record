"""
Internationalisation — English and German.
Call set_language('en' | 'de') once at startup, then use t('key') everywhere.
"""

_lang: str = 'de'

_STRINGS: dict = {
    # ── App ───────────────────────────────────────────────────────────────────
    'app.title':    {'de': 'P2-Record',                    'en': 'P2-Record'},
    'app.subtitle': {'de': 'Game Clip Recorder · Alpha',  'en': 'Game Clip Recorder · Alpha'},

    # ── Update banner ─────────────────────────────────────────────────────────
    'update.available':    {'de': 'Update verfügbar — Version {version}',
                            'en': 'Update available — version {version}'},
    'update.btn':          {'de': 'Wie updaten?', 'en': 'How to update?'},
    'update.dialog.title': {'de': 'Update installieren', 'en': 'Install update'},
    'update.dialog.body':  {'de': 'Führe folgenden Befehl im Terminal aus:',
                            'en': 'Run the following command in your terminal:'},
    'update.dialog.close': {'de': 'Schließen', 'en': 'Close'},
    'update.checking':     {'de': 'Prüfe auf Updates…', 'en': 'Checking for updates…'},
    'update.uptodate':     {'de': 'v{version} · Aktuell', 'en': 'v{version} · Up to date'},
    'update.newer':        {'de': 'v{version} verfügbar', 'en': 'v{version} available'},
    'update.error':        {'de': 'Update-Prüfung fehlgeschlagen', 'en': 'Update check failed'},

    # ── Navigation / sidebar ──────────────────────────────────────────────────
    'nav.dashboard': {'de': 'Dashboard',       'en': 'Dashboard'},
    'nav.library':   {'de': 'Clip-Bibliothek', 'en': 'Clip Library'},
    'nav.settings':  {'de': 'Einstellungen',   'en': 'Settings'},
    'nav.help':      {'de': 'Anleitung',        'en': 'Guide'},
    'rec.off': {'de': '● Nicht aufgenommen', 'en': '● Not recording'},
    'rec.on':  {'de': '● Aufnahme läuft',    'en': '● Recording'},

    # ── Dashboard ─────────────────────────────────────────────────────────────
    'dash.title':         {'de': 'Dashboard',         'en': 'Dashboard'},
    'dash.saved':         {'de': '✓ Gespeichert',      'en': '✓ Saved'},
    'dash.not_recording': {'de': 'Nicht aufgenommen', 'en': 'Not recording'},
    'dash.recording':     {'de': 'Aufnahme läuft',    'en': 'Recording'},
    'dash.no_game':       {'de': 'Kein Spiel erkannt', 'en': 'No game detected'},
    'dash.ring_buffer':   {'de': 'Ring-Buffer',        'en': 'Ring buffer'},
    'dash.actions':       {'de': 'Aktionen',           'en': 'Actions'},
    'dash.start':         {'de': 'Aufnahme starten',  'en': 'Start recording'},
    'dash.stop':          {'de': 'Aufnahme stoppen',  'en': 'Stop recording'},
    'dash.save_clip':     {'de': 'Clip speichern',    'en': 'Save clip'},
    'dash.hotkey_hint':   {'de': 'Hotkey: {key}  ·  Clip-Länge: {dur}', 'en': 'Hotkey: {key}  ·  Clip length: {dur}'},
    'dash.error_prefix':  {'de': 'Fehler: ', 'en': 'Error: '},
    'dash.sec':           {'de': 'Sek',  'en': 'sec'},
    'dash.min':           {'de': 'Min',  'en': 'min'},

    # ── Settings — Monitor ────────────────────────────────────────────────────
    'settings.title':  {'de': 'Einstellungen', 'en': 'Settings'},
    'settings.saved':  {'de': '✓ Gespeichert', 'en': '✓ Saved'},

    'settings.monitor.section':     {'de': 'Bildschirm aufnehmen', 'en': 'Screen capture'},
    'settings.monitor.no_monitors': {'de': 'Keine Monitore erkannt (xrandr nicht verfügbar)', 'en': 'No monitors detected (xrandr not available)'},
    'settings.monitor.wayland_info': {
        'de': ('Wayland: Der aufzunehmende Bildschirm wird beim Start über einen System-Dialog ausgewählt.\n'
               'Änderung hier startet die Aufnahme neu und öffnet den Dialog erneut.'),
        'en': ('Wayland: The screen to capture is selected at startup via a system dialog.\n'
               'Changing this restarts the recording and opens the dialog again.'),
    },
    'settings.monitor.label': {'de': 'Monitor', 'en': 'Monitor'},

    # ── Settings — Hotkeys ────────────────────────────────────────────────────
    'settings.hotkeys.section':     {'de': 'Tastenkürzel', 'en': 'Keyboard shortcuts'},
    'settings.hotkeys.evdev_ok':    {'de': '✓ evdev aktiv — Hotkeys funktionieren im Spiel (Wayland + X11)', 'en': '✓ evdev active — Hotkeys work in-game (Wayland + X11)'},
    'settings.hotkeys.evdev_warn':  {
        'de': ('⚠ Kein evdev-Zugriff — Hotkeys funktionieren möglicherweise nicht im Spiel.\n'
               'Lösung:  sudo usermod -aG input $USER  dann neu einloggen.'),
        'en': ('⚠ No evdev access — Hotkeys may not work in-game.\n'
               'Fix:  sudo usermod -aG input $USER  then re-login.'),
    },
    'settings.hotkeys.save':        {'de': 'Clip speichern',  'en': 'Save clip'},
    'settings.hotkeys.save_hint':   {'de': 'Globaler Hotkey — speichert die letzten N Sekunden', 'en': 'Global hotkey — saves the last N seconds'},
    'settings.hotkeys.toggle':      {'de': 'Aufnahme starten / stoppen', 'en': 'Start / stop recording'},
    'settings.hotkeys.toggle_hint': {'de': 'Leer lassen wenn nicht benötigt', 'en': 'Leave empty if not needed'},
    'settings.hotkeys.capturing':   {'de': '⌨  Taste drücken…', 'en': '⌨  Press a key…'},

    # ── Settings — Recording ──────────────────────────────────────────────────
    'settings.rec.section':         {'de': 'Aufnahme',  'en': 'Recording'},
    'settings.rec.buffer':          {'de': 'Ring-Buffer Dauer',  'en': 'Ring buffer duration'},
    'settings.rec.buffer_hint':     {'de': 'Hält die letzten N Sekunden im Speicher', 'en': 'Keeps the last N seconds in memory'},
    'settings.rec.clip':            {'de': 'Clip-Länge',  'en': 'Clip length'},
    'settings.rec.clip_hint':       {'de': 'Wie viel wird beim Hotkey gespeichert', 'en': 'How much is saved on hotkey press'},
    'settings.rec.quality':         {'de': 'Qualität',  'en': 'Quality'},
    'settings.rec.quality_hint':    {'de': 'Beeinflusst Bitrate der Aufnahme', 'en': 'Affects recording bitrate'},
    'settings.rec.quality_low':     {'de': 'Niedrig · 1,5 Mbit/s', 'en': 'Low · 1.5 Mbit/s'},
    'settings.rec.quality_medium':  {'de': 'Mittel · 3 Mbit/s',    'en': 'Medium · 3 Mbit/s'},
    'settings.rec.quality_high':    {'de': 'Hoch · 5 Mbit/s',      'en': 'High · 5 Mbit/s'},
    'settings.rec.quality_ultra':   {'de': 'Ultra · 8 Mbit/s',     'en': 'Ultra · 8 Mbit/s'},
    'settings.rec.resolution':      {'de': 'Auflösung', 'en': 'Resolution'},
    'settings.rec.resolution_hint': {'de': 'Maximale Aufnahme-Auflösung', 'en': 'Maximum recording resolution'},
    'settings.rec.res_native':      {'de': 'Nativ (Vollbild)', 'en': 'Native (fullscreen)'},
    'settings.rec.fps':             {'de': 'Bildrate',  'en': 'Frame rate'},
    'settings.rec.audio':           {'de': 'Audio',     'en': 'Audio'},
    'settings.rec.audio_hint':      {'de': 'Was soll aufgenommen werden?', 'en': 'What should be recorded?'},
    'settings.rec.audio_none':      {'de': 'Kein Audio',                    'en': 'No audio'},
    'settings.rec.audio_desktop':   {'de': 'Spielton (Desktop)',            'en': 'Game sound (desktop)'},
    'settings.rec.audio_mic':       {'de': 'Mikrofon',                      'en': 'Microphone'},
    'settings.rec.audio_both':      {'de': 'Beides (Desktop + Mikrofon)',   'en': 'Both (Desktop + Mic)'},

    # ── Settings — Output ─────────────────────────────────────────────────────
    'settings.output.section': {'de': 'Speicherort',          'en': 'Save location'},
    'settings.output.folder':  {'de': 'Ordner',               'en': 'Folder'},
    'settings.output.change':  {'de': 'Ändern',               'en': 'Change'},
    'settings.output.dialog':  {'de': 'Ausgabeordner wählen', 'en': 'Select output folder'},

    # ── Settings — Behaviour ──────────────────────────────────────────────────
    'settings.behaviour.section':            {'de': 'Verhalten',               'en': 'Behavior'},
    'settings.behaviour.auto_record':        {'de': 'Automatisch aufnehmen',   'en': 'Auto-record'},
    'settings.behaviour.auto_record_hint':   {'de': 'Startet Aufnahme beim App-Start', 'en': 'Starts recording on app launch'},
    'settings.behaviour.notifications':      {'de': 'Benachrichtigungen',      'en': 'Notifications'},
    'settings.behaviour.notifications_hint': {'de': 'System-Notification bei gespeichertem Clip', 'en': 'System notification when clip is saved'},
    'settings.behaviour.language':           {'de': 'Sprache',                 'en': 'Language'},
    'settings.behaviour.language_hint':      {'de': 'Neustart erforderlich',   'en': 'Restart required'},
    'settings.behaviour.lang_de':            {'de': 'Deutsch',                 'en': 'Deutsch'},
    'settings.behaviour.lang_en':            {'de': 'English',                 'en': 'English'},

    # ── Settings — Info box ───────────────────────────────────────────────────
    'settings.info': {
        'de': ('Clips werden als <b>MP4</b> gespeichert (H.264/AAC via FFmpeg).\n'
               'Für Hardware-Encoding: VAAPI wird automatisch genutzt wenn verfügbar.\n'
               'Für Wayland-Aufnahme: xdg-desktop-portal muss installiert sein.'),
        'en': ('Clips are saved as <b>MP4</b> (H.264/AAC via FFmpeg).\n'
               'Hardware encoding: VAAPI is used automatically when available.\n'
               'For Wayland capture: xdg-desktop-portal must be installed.'),
    },

    # ── Library ───────────────────────────────────────────────────────────────
    'library.title':       {'de': 'Clip-Bibliothek',    'en': 'Clip Library'},
    'library.empty':       {'de': 'Keine Clips gespeichert', 'en': 'No clips saved'},
    'library.open_folder': {'de': 'Ordner öffnen',      'en': 'Open folder'},
    'library.play':        {'de': 'Abspielen',           'en': 'Play'},
    'library.delete':      {'de': 'Löschen',             'en': 'Delete'},

    # ── Help ──────────────────────────────────────────────────────────────────
    'help.title': {'de': 'Anleitung', 'en': 'Guide'},

    'help.s1.title': {'de': 'Was ist der Ring-Buffer?', 'en': 'What is the ring buffer?'},
    'help.s1.body': {
        'de': (
            'P2-Record nimmt deinen Bildschirm durchgehend auf und speichert die letzten N Sekunden '
            'in einem Puffer (Ring-Buffer). Ältere Aufnahmen werden automatisch gelöscht, '
            'sodass immer nur die letzten z. B. 120 Sekunden im Speicher liegen.\n\n'
            'Der Puffer läuft still im Hintergrund — du musst nicht wissen, wann etwas Gutes '
            'passiert. Drückst du F9, werden die letzten Sekunden als MP4 gespeichert.'
        ),
        'en': (
            'P2-Record continuously records your screen and keeps the last N seconds '
            'in a ring buffer. Older footage is discarded automatically, '
            'so only the last e.g. 120 seconds stay in memory.\n\n'
            "The buffer runs silently in the background — you don't need to know when something good happens. "
            'Press F9 and the last N seconds are saved as an MP4.'
        ),
    },

    'help.s2.title': {'de': 'Warum muss die Aufnahme laufen?', 'en': 'Why must recording be active?'},
    'help.s2.body': {
        'de': (
            'Der Ring-Buffer funktioniert nur, wenn die Aufnahme aktiv ist. '
            'P2-Record startet sie automatisch beim App-Start (einstellbar unter Einstellungen → '
            '"Automatisch aufnehmen").\n\n'
            'Solange "● Aufnahme läuft" unten links leuchtet, wird alles mitgeschnitten. '
            'Nichts wird gespeichert, bis du F9 drückst.'
        ),
        'en': (
            'The ring buffer only works when recording is active. '
            'P2-Record starts it automatically on launch (configurable under Settings → '
            '"Auto-record").\n\n'
            'As long as "● Recording" is shown at the bottom left, everything is being captured. '
            'Nothing is saved until you press F9.'
        ),
    },

    'help.s3.title': {'de': 'Clip speichern mit F9', 'en': 'Save a clip with F9'},
    'help.s3.body': {
        'de': (
            '1. Starte das Spiel oder die Anwendung.\n'
            '2. Warte, bis der Buffer voll ist (grüner Balken auf dem Dashboard).\n'
            '3. Nach einem guten Moment: F9 drücken → die letzten N Sekunden werden als MP4 gespeichert.\n'
            '4. Du hörst einen Ton und siehst die Meldung "Clip gespeichert".\n\n'
            'Hinweis: Mindestens 5 Sekunden nach dem Start warten, '
            'bevor der erste Clip gespeichert werden kann.'
        ),
        'en': (
            '1. Launch your game or application.\n'
            '2. Wait for the buffer to fill (green bar on the Dashboard).\n'
            '3. After a good moment: press F9 → the last N seconds are saved as an MP4.\n'
            '4. You will hear a sound and see the "Clip saved" message.\n\n'
            'Note: Wait at least 5 seconds after start before the first clip can be saved.'
        ),
    },

    'help.s4.title': {'de': 'Wayland & Bildschirmfreigabe', 'en': 'Wayland & screen sharing'},
    'help.s4.body': {
        'de': (
            'Da P2-Record auf Wayland läuft, muss die Bildschirmaufnahme über einen '
            'System-Dialog freigegeben werden. Dieser erscheint beim ersten Start.\n\n'
            'Die Auswahl wird gespeichert — beim nächsten Start erscheint kein Dialog mehr. '
            'Möchtest du den Monitor wechseln: Einstellungen → Bildschirm aufnehmen → '
            'anderen Monitor auswählen → Dialog erscheint erneut.'
        ),
        'en': (
            'Since P2-Record runs on Wayland, screen capture must be authorized via a '
            'system dialog. This appears on first launch.\n\n'
            'The selection is saved — no dialog on subsequent starts. '
            'To switch monitors: Settings → Screen capture → select a different monitor → '
            'the dialog will appear again.'
        ),
    },

    'help.s5.title': {'de': 'Audio aufnehmen', 'en': 'Recording audio'},
    'help.s5.body': {
        'de': (
            '"Spielton (Desktop)" nimmt alle Systemklänge mit — Spiel, Musik, Benachrichtigungen.\n'
            '"Mikrofon" nimmt nur das Mikrofon auf.\n'
            '"Beides" mischt Desktop-Ton und Mikrofon in einer Spur.\n'
            '"Kein Audio" speichert nur Video.\n\n'
            'Tipp: Für Game-Clips mit Kommentar "Beides" wählen.'
        ),
        'en': (
            '"Game sound (desktop)" captures all system audio — game, music, notifications.\n'
            '"Microphone" captures only the microphone.\n'
            '"Both" mixes desktop audio and microphone into a single track.\n'
            '"No audio" saves video only.\n\n'
            'Tip: For game clips with commentary, choose "Both".'
        ),
    },

    'help.s6.title': {'de': 'Hotkeys', 'en': 'Hotkeys'},
    'help.s6.body': {
        'de': (
            'F9 (Standard)    → Clip speichern\n'
            'Toggle-Hotkey    → Aufnahme manuell starten / stoppen (optional)\n\n'
            'Hotkeys lassen sich unter Einstellungen → Tastenkürzel ändern.\n\n'
            'Hinweis: Damit Hotkeys im Spiel (Vollbild) funktionieren, '
            'muss dein Benutzer in der Gruppe "input" sein:\n'
            '  sudo usermod -aG input $USER\n'
            'Danach neu einloggen.'
        ),
        'en': (
            'F9 (default)     → Save clip\n'
            'Toggle hotkey    → Start / stop recording manually (optional)\n\n'
            'Hotkeys can be changed under Settings → Keyboard shortcuts.\n\n'
            'Note: For hotkeys to work in-game (fullscreen), '
            'your user must be in the "input" group:\n'
            '  sudo usermod -aG input $USER\n'
            'Then log out and back in.'
        ),
    },

    'help.s7.title': {'de': 'Ausgabe-Dateien', 'en': 'Output files'},
    'help.s7.body': {
        'de': (
            'Clips werden als MP4 (H.264/AAC) im Ordner ~/Videos/P2-Record gespeichert.\n'
            'Dateiname: DATUM_UHRZEIT_Spielname.mp4\n\n'
            'In der Clip-Bibliothek kannst du Clips abspielen, '
            'den Ordner öffnen oder Clips löschen.'
        ),
        'en': (
            'Clips are saved as MP4 (H.264/AAC) in ~/Videos/P2-Record.\n'
            'Filename: DATE_TIME_GameName.mp4\n\n'
            'In the Clip Library you can play clips, open the folder, or delete clips.'
        ),
    },

    # ── App-level messages ────────────────────────────────────────────────────
    'app.no_clip':         {'de': 'Noch kein Clip — mindestens 5 Sekunden nach Start warten.', 'en': 'No clip yet — wait at least 5 seconds after start.'},
    'app.clip_saved_title': {'de': 'Clip gespeichert', 'en': 'Clip saved'},
}


def t(lookup: str, **kwargs) -> str:
    entry = _STRINGS.get(lookup)
    if entry is None:
        return lookup
    text = entry.get(_lang) or entry.get('en') or lookup
    return text.format(**kwargs) if kwargs else text


def set_language(lang: str) -> None:
    global _lang
    if lang in ('de', 'en'):
        _lang = lang


def get_language() -> str:
    return _lang
