import json
import threading
import urllib.request
from typing import Callable, Optional

CURRENT_VERSION = '0.2.6'
_TAGS_URL = 'https://api.github.com/repos/Varionetzwerk/p2record/tags'


def _parse(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip('v').split('.')[:4])
    except Exception:
        return (0,)


def is_newer(latest: str) -> bool:
    return _parse(latest) > _parse(CURRENT_VERSION)


def check_for_update(callback: Callable[[Optional[str]], None]) -> None:
    """Background check. Calls callback(latest_tag) if newer, else callback(None)."""
    def _run():
        try:
            req = urllib.request.Request(
                _TAGS_URL,
                headers={'User-Agent': f'p2record/{CURRENT_VERSION}'},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                tags = json.loads(resp.read())
            if not tags:
                callback(None)
                return
            latest = tags[0]['name'].lstrip('v')
            callback(latest if is_newer(latest) else None)
        except Exception:
            callback(None)

    threading.Thread(target=_run, daemon=True).start()
