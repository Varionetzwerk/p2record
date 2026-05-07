import os
from pathlib import Path
from typing import Callable, Optional

from gi.repository import GLib

# Known games: process name → display name
KNOWN_GAMES: dict[str, str] = {
    'cs2':              'Counter-Strike 2',
    'csgo':             'CS:GO',
    'dota2':            'Dota 2',
    'hl2_linux':        'Half-Life 2',
    'RocketLeague':     'Rocket League',
    'cyberpunk2077':    'Cyberpunk 2077',
    'witcher3':         'The Witcher 3',
    'eldenring':        'Elden Ring',
    'darksouls3':       'Dark Souls III',
    'sekiro':           'Sekiro',
    'ac_odyssey':       'Assassin\'s Creed Odyssey',
    'valheim':          'Valheim',
    'factorio':         'Factorio',
    'Minecraft':        'Minecraft',
    'javaw':            'Minecraft (Java)',
    'GenshinImpact':    'Genshin Impact',
    'LeagueOfLegends':  'League of Legends',
    'wine':             'Wine Game',
    'wine64':           'Wine Game (64-bit)',
    'proton':           'Proton Game',
    'steamwebhelper':   None,  # ignore steam helper
    'steam':            None,
    'gamescope':        None,
    'MangoHud':         None,
}

POLL_MS = 2500


class GameDetector:
    def __init__(self, on_changed: Callable[[Optional[str]], None]):
        self._on_changed = on_changed
        self._current: Optional[str] = None
        self._timer_id: Optional[int] = None

    def start(self) -> None:
        self._timer_id = GLib.timeout_add(POLL_MS, self._poll)
        self._poll()

    def stop(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _poll(self) -> bool:
        found = self._scan()
        if found != self._current:
            self._current = found
            self._on_changed(found)
        return True  # keep timer alive

    def _scan(self) -> Optional[str]:
        proc = Path('/proc')
        try:
            pids = [p for p in proc.iterdir() if p.name.isdigit()]
        except PermissionError:
            return None

        for pid_dir in pids:
            comm_file = pid_dir / 'comm'
            try:
                comm = comm_file.read_text().strip()
            except (PermissionError, FileNotFoundError):
                continue

            if comm in KNOWN_GAMES:
                display = KNOWN_GAMES[comm]
                if display is not None:
                    return display
                continue

            # Fuzzy: check if any known key is a substring of comm or vice-versa
            lower_comm = comm.lower()
            for key, display in KNOWN_GAMES.items():
                if display and (key.lower() in lower_comm or lower_comm in key.lower()):
                    return display

        return None
