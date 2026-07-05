"""
xdg-desktop-portal ScreenCast — Wayland screen capture via PipeWire.

Key detail: the portal creates an ISOLATED PipeWire remote. The node_id only
exists inside that remote, not in the global PipeWire server. We must call
OpenPipeWireRemote() to get a private fd and pass it to gst-launch (pipewiresrc
fd=<pw_fd> path=<node_id>). Without this, gst says "target not found".

The GLib main loop in the portal thread must keep running for the full
recording session so D-Bus keepalives are dispatched and the session stays alive.
"""

import os
import random
import threading
from pathlib import Path
from typing import Callable, Optional

_TOKEN_FILE = Path.home() / '.config' / 'p2record' / 'portal_token.txt'
_PORTAL_BUS = 'org.freedesktop.portal.Desktop'
_PORTAL_OBJ = '/org/freedesktop/portal/desktop'
_SCREENCAST  = 'org.freedesktop.portal.ScreenCast'
_REQUEST_IF  = 'org.freedesktop.portal.Request'


def _rand_token() -> str:
    return ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=8))


def _load_token() -> str:
    try:
        return _TOKEN_FILE.read_text().strip()
    except Exception:
        return ''


def _save_token(token: str) -> None:
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(token)
    except Exception:
        pass


def clear_restore_token() -> None:
    """Delete the saved restore token so the portal dialog appears again."""
    try:
        _TOKEN_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def request_screencast_node(
    callback: Callable[[Optional[int], int, int, int], None],
    stop_event: threading.Event,
) -> None:
    """
    Async: request a Wayland ScreenCast session from xdg-desktop-portal.

    callback(node_id, width, height, pw_fd) on the GTK main loop.
    pw_fd is the PipeWire remote file descriptor — pass it to pipewiresrc.
    On failure: callback(None, 0, 0, -1).

    The portal thread's GLib main loop keeps running until stop_event is set.
    """
    t = threading.Thread(
        target=_portal_thread,
        args=(callback, stop_event),
        daemon=True,
    )
    t.start()


def _portal_thread(callback: Callable, stop_event: threading.Event) -> None:
    try:
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as e:
        print(f'[Portal] Import error: {e}')
        from gi.repository import GLib
        GLib.idle_add(lambda: callback(None, 0, 0, -1) or False)
        return

    ml   = dbus.mainloop.glib.DBusGMainLoop()
    loop = GLib.MainLoop()
    result: dict = {'node_id': None, 'width': 0, 'height': 0, 'pw_fd': -1}

    def _notify(success: bool = True):
        from gi.repository import GLib as _G
        _G.idle_add(
            lambda: callback(
                result['node_id'], result['width'], result['height'], result['pw_fd']
            ) or False
        )
        if not success:
            loop.quit()

    def _check_stop() -> bool:
        if stop_event.is_set():
            loop.quit()
            return False
        return True

    try:
        bus    = dbus.SessionBus(mainloop=ml)
        sender = bus.get_unique_name().lstrip(':').replace('.', '_')
        portal = bus.get_object(_PORTAL_BUS, _PORTAL_OBJ)
        sc     = dbus.Interface(portal, _SCREENCAST)

        # ── 1. CreateSession ───────────────────────────────────────────────────
        sess_tok  = _rand_token()
        req1_tok  = _rand_token()
        req1_path = f'/org/freedesktop/portal/desktop/request/{sender}/{req1_tok}'
        session_handle: list = [None]

        def on_create(response, results):
            if response != 0:
                print(f'[Portal] CreateSession failed (code={response})')
                _notify(success=False)
                return
            session_handle[0] = str(results.get('session_handle', ''))
            _select_sources()

        dbus.Interface(
            bus.get_object(_PORTAL_BUS, req1_path), _REQUEST_IF
        ).connect_to_signal('Response', on_create)
        sc.CreateSession(dbus.Dictionary({
            'handle_token':        dbus.String(req1_tok),
            'session_handle_token': dbus.String(sess_tok),
        }, signature='sv'))

        # ── 2. SelectSources ───────────────────────────────────────────────────
        def _select_sources():
            req2_tok  = _rand_token()
            req2_path = f'/org/freedesktop/portal/desktop/request/{sender}/{req2_tok}'
            restore   = _load_token()
            opts = dbus.Dictionary({
                'handle_token': dbus.String(req2_tok),
                'types':        dbus.UInt32(1),    # MONITOR
                'multiple':     dbus.Boolean(False),
                'persist_mode': dbus.UInt32(2),    # persistent
                'cursor_mode':  dbus.UInt32(1),    # embedded in stream
            }, signature='sv')
            if restore:
                opts['restore_token'] = dbus.String(restore)

            def on_select(response, results):
                if response != 0:
                    print(f'[Portal] SelectSources failed (code={response})')
                    _notify(success=False)
                    return
                _start()

            dbus.Interface(
                bus.get_object(_PORTAL_BUS, req2_path), _REQUEST_IF
            ).connect_to_signal('Response', on_select)
            sc.SelectSources(session_handle[0], opts)

        # ── 3. Start ───────────────────────────────────────────────────────────
        def _start():
            req3_tok  = _rand_token()
            req3_path = f'/org/freedesktop/portal/desktop/request/{sender}/{req3_tok}'

            def on_start(response, results):
                if response != 0:
                    print(f'[Portal] Start failed (code={response})')
                    _notify(success=False)
                    return

                new_tok = str(results.get('restore_token', ''))
                if new_tok:
                    _save_token(new_tok)

                streams = results.get('streams', [])
                if not streams:
                    print('[Portal] Keine Streams zurückgegeben')
                    _notify(success=False)
                    return

                node_id = int(streams[0][0])
                props   = dict(streams[0][1])
                size    = props.get('size', None)
                if size:
                    result['width']  = int(size[0])
                    result['height'] = int(size[1])
                result['node_id'] = node_id

                # ── 4. OpenPipeWireRemote ──────────────────────────────────────
                # The node lives in an ISOLATED PipeWire remote — get the fd.
                try:
                    fd_obj = sc.OpenPipeWireRemote(
                        session_handle[0],
                        dbus.Dictionary({}, signature='sv'),
                    )
                    result['pw_fd'] = fd_obj.take()
                    print(f'[Portal] PipeWire node {node_id}  '
                          f'({result["width"]}×{result["height"]})  '
                          f'fd={result["pw_fd"]}')
                except Exception as e:
                    print(f'[Portal] OpenPipeWireRemote fehlgeschlagen: {e}')
                    _notify(success=False)
                    return

                GLib.timeout_add(500, _check_stop)
                _notify(success=True)

            dbus.Interface(
                bus.get_object(_PORTAL_BUS, req3_path), _REQUEST_IF
            ).connect_to_signal('Response', on_start)
            sc.Start(session_handle[0], '', dbus.Dictionary({
                'handle_token': dbus.String(req3_tok),
            }, signature='sv'))

        loop.run()
        print('[Portal] Portal-Session beendet.')

    except Exception as exc:
        print(f'[Portal] Exception: {exc}')
        try:
            from gi.repository import GLib as _G
            _G.idle_add(lambda: callback(None, 0, 0, -1) or False)
        except Exception:
            pass
