from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ObsidianNoteTarget:
    vault_path: Path
    note_relpath: str

    @property
    def note_path(self) -> Path:
        return self.vault_path / self.note_relpath


def resolve_target_from_config(obs: dict[str, Any], *, default_filename: str) -> ObsidianNoteTarget | None:
    vault_path_raw = obs.get("vault_path")
    if not vault_path_raw:
        return None

    note_relpath = obs.get("note_relpath")
    if note_relpath:
        return ObsidianNoteTarget(vault_path=Path(str(vault_path_raw)).expanduser(), note_relpath=str(note_relpath))

    logs_dir_relpath = obs.get("logs_dir_relpath")
    if not logs_dir_relpath:
        return None

    filename = obs.get("filename") or default_filename
    note_path = Path(str(logs_dir_relpath)) / str(filename)
    return ObsidianNoteTarget(vault_path=Path(str(vault_path_raw)).expanduser(), note_relpath=str(note_path))


def append_markdown(target: ObsidianNoteTarget, markdown: str) -> Path:
    note_path = target.note_path
    note_path.parent.mkdir(parents=True, exist_ok=True)

    text = markdown.rstrip("\n") + "\n"
    with note_path.open("a", encoding="utf-8") as f:
        f.write(text)

    return note_path


def replace_markdown(target: ObsidianNoteTarget, markdown: str) -> Path:
    note_path = target.note_path
    note_path.parent.mkdir(parents=True, exist_ok=True)

    text = markdown.rstrip("\n") + "\n"
    with note_path.open("w", encoding="utf-8") as f:
        f.write(text)

    return note_path


def format_section(title: str, lines: list[str], *, now: datetime | None = None) -> str:
    ts = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    out: list[str] = []
    out.append(f"## {title} ({ts})")
    out.extend(lines)
    out.append("")
    return "\n".join(out)
