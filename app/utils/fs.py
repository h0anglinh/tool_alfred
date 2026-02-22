from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MoveResult:
    moved: bool
    src: Path
    dest: Path
    reason: str | None = None


def matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def is_recent(path: Path, min_age_seconds: int) -> bool:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return True
    return (time.time() - mtime) < min_age_seconds


def is_in_top_folder(path: Path, root: Path, top_folders: set[str]) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if not rel.parts:
        return True
    return rel.parts[0] in top_folders


def unique_target_path(dest_dir: Path, filename: str) -> Path:
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 2
    while True:
        alt = dest_dir / f"{stem} ({i}){suffix}"
        if not alt.exists():
            return alt
        i += 1


def atomic_move(src: Path, dest: Path) -> None:
    ensure_dir(dest.parent)
    os.replace(src, dest)