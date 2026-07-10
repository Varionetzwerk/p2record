import json
import os
from pathlib import Path

DEFAULTS: dict = {
    'buffer_duration': 120,
    'clip_duration': 60,
    'quality': 'high',
    'fps': 30,
    'resolution': 'native',
    'output_path': str(Path.home() / 'Videos' / 'P2-Record'),
    'save_hotkey': 'F9',
    'toggle_hotkey': '',
    'audio_source': 'desktop',  # 'none' | 'desktop' | 'mic' | 'both'
    'timestamp_position': 'off',  # 'off' | 'top-left' | 'top-center' | 'top-right'
                                  # | 'bottom-left' | 'bottom-center' | 'bottom-right'
    'capture_monitor': '',      # monitor name, e.g. "HDMI-A-1"; '' = primary
    'minimize_to_tray': True,
    'show_notifications': True,
    'auto_record': True,
    'language': 'de',           # 'de' | 'en'
}

_CONFIG_DIR = Path.home() / '.config' / 'p2record'
_CONFIG_FILE = _CONFIG_DIR / 'settings.json'


class Settings:
    def __init__(self):
        self._data: dict = {}
        self._listeners: list = []
        self._load()

    def _load(self):
        if _CONFIG_FILE.exists():
            try:
                raw = json.loads(_CONFIG_FILE.read_text())
                self._data = {**DEFAULTS, **raw}
                return
            except Exception:
                pass
        self._data = dict(DEFAULTS)

    def _save(self):
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(json.dumps(self._data, indent=2))
        except OSError as e:
            print(f'[Settings] Speichern fehlgeschlagen: {e}')

    def get(self, key: str, fallback=None):
        return self._data.get(key, DEFAULTS.get(key, fallback))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()
        for cb in self._listeners:
            cb(key, value)

    def set_many(self, patch: dict) -> None:
        self._data.update(patch)
        self._save()
        for key, value in patch.items():
            for cb in self._listeners:
                cb(key, value)

    def all(self) -> dict:
        return dict(self._data)

    def connect_changed(self, callback) -> None:
        self._listeners.append(callback)
