"""
Hotkey manager — drei Backends in Prioritätsreihenfolge:

1. evdev   — /dev/input/event* lesen, funktioniert auch im Spiel auf Wayland + X11
             Voraussetzung: sudo usermod -aG input $USER  und neu einloggen
2. X11     — XGrabKey über python-xlib, funktioniert auf X11 und XWayland
             Kein Root nötig, aber nicht in exklusiven Vollbild-Spielen
3. Kein Hotkey — Fehlermeldung
"""

import os
import selectors
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from gi.repository import GLib

# ── evdev ──────────────────────────────────────────────────────────────────────
try:
    import evdev
    from evdev import ecodes as _ecodes
    _EVDEV_OK = True
except ImportError:
    _EVDEV_OK = False

# ── python-xlib ────────────────────────────────────────────────────────────────
try:
    from Xlib.display import Display as _XDisplay
    from Xlib import X as _X, XK as _XK, error as _Xerror
    _XLIB_OK = True
except ImportError:
    _XLIB_OK = False


# ── Key-Name → evdev-Code ──────────────────────────────────────────────────────
_NAME_TO_EVDEV: Dict[str, int] = {}

def _build_evdev_map() -> None:
    if not _EVDEV_OK:
        return
    for name, code in _ecodes.keys.items():
        if isinstance(name, str) and name.startswith('KEY_'):
            _NAME_TO_EVDEV[name[4:]] = code   # "KEY_F9" → {"F9": 67}

_build_evdev_map()

_MODIFIER_EVDEV = {
    'Control': ['KEY_LEFTCTRL',  'KEY_RIGHTCTRL'],
    'Ctrl':    ['KEY_LEFTCTRL',  'KEY_RIGHTCTRL'],
    'Alt':     ['KEY_LEFTALT',   'KEY_RIGHTALT'],
    'Shift':   ['KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT'],
    'Super':   ['KEY_LEFTMETA',  'KEY_RIGHTMETA'],
    'Meta':    ['KEY_LEFTMETA',  'KEY_RIGHTMETA'],
}

# ── Key-Name → X11-Keysym ──────────────────────────────────────────────────────
_MODIFIER_X11 = {
    'Control': _X.ControlMask if _XLIB_OK else 0,
    'Ctrl':    _X.ControlMask if _XLIB_OK else 0,
    'Alt':     _X.Mod1Mask    if _XLIB_OK else 0,
    'Shift':   _X.ShiftMask   if _XLIB_OK else 0,
    'Super':   _X.Mod4Mask    if _XLIB_OK else 0,
    'Meta':    _X.Mod4Mask    if _XLIB_OK else 0,
}


def _parse_accel_evdev(accel: str):
    """'Control+F9' → (modifier_code_set, key_code | None)"""
    parts = accel.split('+')
    mods: set = set()
    code: Optional[int] = None
    for part in parts:
        if part in _MODIFIER_EVDEV:
            for evname in _MODIFIER_EVDEV[part]:
                if _EVDEV_OK and hasattr(_ecodes, evname):
                    mods.add(getattr(_ecodes, evname))
        else:
            evname = f'KEY_{part.upper()}'
            if _EVDEV_OK and hasattr(_ecodes, evname):
                code = getattr(_ecodes, evname)
    return mods, code


def _parse_accel_x11(accel: str):
    """'Control+F9' → (x11_mod_mask, keysym | None)"""
    if not _XLIB_OK:
        return 0, None
    parts = accel.split('+')
    modmask = 0
    keysym = None
    for part in parts:
        if part in _MODIFIER_X11:
            modmask |= _MODIFIER_X11[part]
        else:
            ks = _XK.string_to_keysym(part)
            if ks == 0:
                ks = _XK.string_to_keysym(f'F{part[1:]}') if part.startswith('F') else 0
            if ks != 0:
                keysym = ks
    return modmask, keysym


# ══════════════════════════════════════════════════════════════════════════════
class HotkeyManager:

    def __init__(self):
        self._hotkeys_evdev: Dict[int, Tuple[set, Callable]] = {}
        self._hotkeys_x11:   Dict[int, Tuple[int, Callable]] = {}  # keycode → (modmask, cb)
        self._pressed: set = set()

        self._evdev_devices: list = []
        self._evdev_thread: Optional[threading.Thread] = None

        self._x11_display = None
        self._x11_thread: Optional[threading.Thread] = None

        self._running = False
        self.using_evdev = False
        self.using_x11   = False

    # ── Public ─────────────────────────────────────────────────────────────────

    def init(self) -> str:
        """Start best available backend. Returns 'evdev' | 'x11' | 'none'."""
        if _EVDEV_OK and self._try_evdev():
            self.using_evdev = True
            print('[Hotkeys] Backend: evdev (funktioniert im Spiel)')
            return 'evdev'

        if _XLIB_OK and os.environ.get('DISPLAY') and self._try_x11():
            self.using_x11 = True
            print('[Hotkeys] Backend: X11/XWayland (funktioniert auf Desktop)')
            return 'x11'

        print('[Hotkeys] Kein Hotkey-Backend verfügbar.')
        print('[Hotkeys] Für In-Game-Hotkeys: sudo usermod -aG input $USER  dann neu einloggen')
        return 'none'

    def destroy(self) -> None:
        self._running = False
        for dev in self._evdev_devices:
            try:
                dev.close()
            except Exception:
                pass
        if self._x11_display:
            try:
                self._x11_display.close()
            except Exception:
                pass

    def register(self, accel: str, callback: Callable) -> None:
        if not accel:
            return
        if self.using_evdev:
            self._register_evdev(accel, callback)
        elif self.using_x11:
            self._register_x11(accel, callback)

    def unregister_all(self) -> None:
        self._hotkeys_evdev.clear()
        if self.using_x11 and self._x11_display:
            try:
                root = self._x11_display.screen().root
                root.ungrab_key(_X.AnyKey, _X.AnyModifier)
                self._x11_display.flush()
            except Exception:
                pass
        self._hotkeys_x11.clear()

    # ── evdev backend ──────────────────────────────────────────────────────────

    def _try_evdev(self) -> bool:
        keyboards = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if _ecodes.EV_KEY in caps:
                    keys = caps[_ecodes.EV_KEY]
                    if _ecodes.KEY_A in keys or _ecodes.KEY_F9 in keys:
                        keyboards.append(dev)
            except Exception:
                pass
        if not keyboards:
            print('[Hotkeys] evdev: kein Zugriff auf /dev/input')
            print('[Hotkeys] → sudo usermod -aG input $USER  dann neu einloggen')
            return False
        self._evdev_devices = keyboards
        self._running = True
        self._evdev_thread = threading.Thread(target=self._evdev_loop, daemon=True)
        self._evdev_thread.start()
        return True

    def _register_evdev(self, accel: str, callback: Callable) -> None:
        mods, code = _parse_accel_evdev(accel)
        if code is None:
            print(f'[Hotkeys] evdev: unbekannte Taste {accel!r}')
            return
        self._hotkeys_evdev[code] = (mods, callback)
        print(f'[Hotkeys] Registriert (evdev): {accel}')

    def _evdev_loop(self) -> None:
        sel = selectors.DefaultSelector()
        for dev in self._evdev_devices:
            try:
                sel.register(dev, selectors.EVENT_READ)
            except Exception:
                pass
        while self._running:
            try:
                ready = sel.select(timeout=0.5)
            except Exception:
                break
            for key, _ in ready:
                dev = key.fileobj
                try:
                    for event in dev.read():
                        if event.type == _ecodes.EV_KEY:
                            if event.value == 1:
                                self._pressed.add(event.code)
                                self._fire_evdev(event.code)
                            elif event.value == 0:
                                self._pressed.discard(event.code)
                except OSError:
                    pass
        sel.close()

    def _fire_evdev(self, code: int) -> None:
        if code not in self._hotkeys_evdev:
            return
        mods, cb = self._hotkeys_evdev[code]
        if mods and not mods.intersection(self._pressed):
            return
        GLib.idle_add(cb)

    # ── X11 backend ────────────────────────────────────────────────────────────

    def _try_x11(self) -> bool:
        try:
            self._x11_display = _XDisplay()
            self._running = True
            self._x11_thread = threading.Thread(target=self._x11_loop, daemon=True)
            self._x11_thread.start()
            return True
        except Exception as e:
            print(f'[Hotkeys] X11: Fehler beim Verbinden: {e}')
            return False

    def _register_x11(self, accel: str, callback: Callable) -> None:
        modmask, keysym = _parse_accel_x11(accel)
        if keysym is None:
            print(f'[Hotkeys] X11: unbekannte Taste {accel!r}')
            return
        keycode = self._x11_display.keysym_to_keycode(keysym)
        if keycode == 0:
            print(f'[Hotkeys] X11: kein Keycode für {accel!r}')
            return

        root = self._x11_display.screen().root
        # Grab with and without CapsLock / NumLock
        for extra in [0, _X.LockMask, _X.Mod2Mask, _X.LockMask | _X.Mod2Mask]:
            try:
                root.grab_key(keycode, modmask | extra, True,
                              _X.GrabModeAsync, _X.GrabModeAsync)
            except Exception:
                pass
        self._x11_display.flush()
        self._hotkeys_x11[keycode] = (modmask, callback)
        print(f'[Hotkeys] Registriert (X11): {accel}  keycode={keycode}')

    def _x11_loop(self) -> None:
        if not self._x11_display:
            return
        try:
            # Do NOT set KeyPressMask on root — grab_key delivers events
            # to root automatically; KeyPressMask would flood ALL key events
            self._x11_display.flush()
        except Exception:
            return

        import time
        _last_fire: dict = {}  # debounce auto-repeat (400ms cooldown)

        while self._running:
            try:
                if self._x11_display.pending_events() == 0:
                    time.sleep(0.05)
                    continue
                event = self._x11_display.next_event()
                if event.type == _X.KeyPress:
                    now = time.monotonic()
                    if now - _last_fire.get(event.detail, 0) > 0.4:
                        _last_fire[event.detail] = now
                        self._fire_x11(event.detail, event.state)
            except Exception:
                break

    def _fire_x11(self, keycode: int, state: int) -> None:
        if keycode not in self._hotkeys_x11:
            return
        modmask, cb = self._hotkeys_x11[keycode]
        # Ignore lock keys in state comparison
        clean = state & ~(_X.LockMask | _X.Mod2Mask)
        if modmask != 0 and (clean & modmask) != modmask:
            return
        GLib.idle_add(cb)
