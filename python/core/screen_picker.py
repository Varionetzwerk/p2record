"""Enumerate connected monitors via xrandr."""

import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Monitor:
    name: str
    width: int
    height: int
    x: int
    y: int
    primary: bool

    def label(self) -> str:
        tag = ' (Primär)' if self.primary else ''
        return f'{self.name}  {self.width}×{self.height}{tag}'

    def xgrab_input(self, display: str) -> List[str]:
        """Returns ffmpeg x11grab -video_size / -i arguments for this monitor."""
        return [
            '-video_size', f'{self.width}x{self.height}',
            '-i', f'{display}+{self.x},{self.y}',
        ]


def list_monitors() -> List[Monitor]:
    try:
        r = subprocess.run(['xrandr', '--listmonitors'],
                           capture_output=True, text=True, timeout=3)
    except Exception:
        return []

    monitors = []
    # Line format: " 0: +*HDMI-A-1 1680/433x1050/271+0+0  HDMI-A-1"
    pattern = re.compile(
        r'^\s*\d+:\s*\+(\*?)(\S+)\s+(\d+)/\d+x(\d+)/\d+\+(\d+)\+(\d+)'
    )
    for line in r.stdout.splitlines():
        m = pattern.match(line)
        if m:
            monitors.append(Monitor(
                name=m.group(2),
                width=int(m.group(3)),
                height=int(m.group(4)),
                x=int(m.group(5)),
                y=int(m.group(6)),
                primary=bool(m.group(1)),
            ))
    return monitors


def find_monitor(name: str, monitors: Optional[List[Monitor]] = None) -> Optional[Monitor]:
    if monitors is None:
        monitors = list_monitors()
    for m in monitors:
        if m.name == name:
            return m
    return None
