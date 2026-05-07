import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.settings import Settings


@dataclass
class Clip:
    id: str
    name: str
    game_name: str
    file_path: str
    thumbnail_path: Optional[str]
    duration: float   # seconds
    size: int         # bytes
    created_at: str


class ClipManager:
    def __init__(self, settings: Settings):
        self._settings = settings

    def list_clips(self) -> List[Clip]:
        output_dir = Path(self._settings.get('output_path'))
        if not output_dir.exists():
            return []

        clips = []
        for f in sorted(output_dir.glob('*.mp4'), key=lambda p: p.stat().st_mtime, reverse=True):
            clip = self._make_clip(f)
            if clip:
                clips.append(clip)
        return clips

    def delete_clip(self, file_path: str) -> bool:
        p = Path(file_path)
        thumb = p.with_suffix('.jpg')
        try:
            p.unlink(missing_ok=True)
            thumb.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def open_folder(self, file_path: str) -> None:
        folder = str(Path(file_path).parent)
        subprocess.Popen(['xdg-open', folder])

    def generate_thumbnail(self, file_path: str) -> Optional[str]:
        thumb = Path(file_path).with_suffix('.jpg')
        if thumb.exists():
            return str(thumb)
        cmd = [
            'ffmpeg', '-y', '-ss', '00:00:01', '-i', file_path,
            '-vframes', '1', '-q:v', '3',
            '-vf', 'scale=320:180:force_original_aspect_ratio=decrease',
            str(thumb),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return str(thumb) if result.returncode == 0 and thumb.exists() else None
        except Exception:
            return None

    def _make_clip(self, path: Path) -> Optional[Clip]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None

        duration = self._probe_duration(path)
        game_name, created_str = self._parse_filename(path.stem)
        thumb = path.with_suffix('.jpg')

        return Clip(
            id=path.stem,
            name=path.stem,
            game_name=game_name,
            file_path=str(path),
            thumbnail_path=str(thumb) if thumb.exists() else None,
            duration=duration,
            size=stat.st_size,
            created_at=created_str,
        )

    def _probe_duration(self, path: Path) -> float:
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                capture_output=True, text=True, timeout=5,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _parse_filename(self, stem: str):
        # Format: 2024-01-15_21-30-45_GameName
        parts = stem.split('_', 2)
        if len(parts) == 3:
            date_str, time_str, game = parts
            try:
                dt = datetime.strptime(f'{date_str}_{time_str}', '%Y-%m-%d_%H-%M-%S')
                return game.replace('_', ' '), dt.strftime('%d.%m.%Y %H:%M')
            except ValueError:
                pass
        return 'Unknown', ''
