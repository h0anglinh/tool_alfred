from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.features.base import Feature, FeatureContext
from app.utils.fs import (
    atomic_move,
    ensure_dir,
    is_in_top_folder,
    is_recent,
    matches_any,
    unique_target_path,
)
from app.utils.log import Logger
from app.utils.obsidian import append_markdown, format_section, resolve_target_from_config


@dataclass(frozen=True)
class JanitorSettings:
    root: Path
    scan_interval_seconds: int
    min_file_age_seconds: int
    dry_run: bool
    ignore: list[str]
    protected_folders: list[str]
    folders: dict[str, str]
    obsidian: dict[str, Any]


class DownloadsJanitor(Feature):
    key = "downloads_janitor"

    def run_forever(self, ctx: FeatureContext) -> None:
        cfg = self._load_settings(ctx.config.get(self.key, {}))
        logger = Logger(log_file=Path("/logs/alfred.log"))

        self._bootstrap(cfg, logger)
        logger.info(
            f"Downloads Janitor started (root={cfg.root}, interval={cfg.scan_interval_seconds}s, dry_run={cfg.dry_run})"
        )

        import time

        while True:
            self._scan_once(cfg, logger)
            time.sleep(cfg.scan_interval_seconds)

    def _bootstrap(self, cfg: JanitorSettings, logger: Logger) -> None:
        ensure_dir(cfg.root)
        for _, folder in cfg.folders.items():
            ensure_dir(cfg.root / folder)
        logger.info("Bootstrap complete")

    def _scan_once(self, cfg: JanitorSettings, logger: Logger) -> None:
        root = cfg.root
        protected = set(cfg.protected_folders)

        moved_count = 0
        skipped = 0
        moves: list[tuple[Path, Path]] = []

        for entry in root.iterdir():
            if entry.is_dir():
                continue

            name = entry.name

            if matches_any(name, cfg.ignore):
                skipped += 1
                continue

            if is_recent(entry, cfg.min_file_age_seconds):
                skipped += 1
                continue

            # Nesahej na soubory, které už jsou uvnitř našich cílových složek
            if is_in_top_folder(entry, root, protected):
                skipped += 1
                continue

            key = self._classify(entry)
            dest_dir = root / cfg.folders.get(key, cfg.folders["other"])
            dest = unique_target_path(dest_dir, name)

            if cfg.dry_run:
                logger.info(f"DRY_RUN move: {entry} -> {dest}")
                moved_count += 1
                moves.append((entry, dest))
                continue

            try:
                atomic_move(entry, dest)
                logger.info(f"MOVED: {entry} -> {dest}")
                moved_count += 1
                moves.append((entry, dest))
            except Exception as e:
                logger.error(f"FAILED: {entry} -> {dest} | {e}")

        logger.info(f"Scan done: moved={moved_count}, skipped={skipped}")
        self._maybe_write_obsidian(cfg, moves, moved_count, skipped, logger)

    def _maybe_write_obsidian(
        self,
        cfg: JanitorSettings,
        moves: list[tuple[Path, Path]],
        moved_count: int,
        skipped: int,
        logger: Logger,
    ) -> None:
        obs = cfg.obsidian or {}
        if not bool(obs.get("enabled", False)):
            return
        if not moves:
            return

        vault_path_raw = obs.get("vault_path")
        title = str(obs.get("title", "Alfred • Downloads Janitor"))

        try:
            if not vault_path_raw:
                logger.error("Obsidian enabled but missing obsidian.vault_path")
                return
            target = resolve_target_from_config(obs, default_filename=f"{self.key}.md")
            if not target:
                logger.error(
                    "Obsidian enabled but missing obsidian.note_relpath or obsidian.logs_dir_relpath"
                )
                return

            lines: list[str] = []
            lines.append(f"- moved: **{moved_count}**, skipped: **{skipped}**")
            lines.append("")
            for src, dest in moves:
                try:
                    src_rel = src.relative_to(cfg.root).as_posix()
                except ValueError:
                    src_rel = src.name
                try:
                    dest_rel = dest.relative_to(cfg.root).as_posix()
                except ValueError:
                    dest_rel = dest.name
                lines.append(f"- `{src_rel}` → `{dest_rel}`")

            md = format_section(title, lines)
            note_path = append_markdown(target, md)
            logger.info(f"WROTE obsidian note: {note_path}")
        except Exception as e:
            logger.error(f"FAILED writing Obsidian note: {e}")

    def _classify(self, path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")

        images = {"png", "jpg", "jpeg", "gif", "webp", "svg", "heic", "tiff", "bmp"}
        videos = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}
        audio = {"mp3", "m4a", "aac", "wav", "flac", "ogg"}
        docs = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "rtf", "csv", "mdx"}
        archives = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}
        code = {"js", "jsx", "ts", "tsx", "py", "json", "yml", "yaml", "toml", "ini", "sql", "sh"}
        apps = {"dmg", "pkg"}

        # záměrně NEexistuje fonts/torrents — ty spadnou do "other"
        if ext in images:
            return "images"
        if ext in videos:
            return "videos"
        if ext in audio:
            return "audio"
        if ext in docs:
            return "docs"
        if ext in archives:
            return "archives"
        if ext in code:
            return "code"
        if ext in apps:
            return "apps"
        return "other"

    def _load_settings(self, raw: dict[str, Any]) -> JanitorSettings:
        def p(v: str) -> Path:
            return Path(v)

        folders = raw.get("folders") or {
            "images": "Images",
            "videos": "Videos",
            "audio": "Audio",
            "docs": "Docs",
            "archives": "Archives",
            "code": "Code",
            "apps": "Apps",
            "other": "Other",
        }

        # chráněné = top-level cílové složky; nic dalšího (žádný ByDate)
        protected = raw.get("protected_folders") or list(set(folders.values()))

        return JanitorSettings(
            root=p(raw.get("root", "/downloads")),
            scan_interval_seconds=int(raw.get("scan_interval_seconds", 120)),
            min_file_age_seconds=int(raw.get("min_file_age_seconds", 60)),
            dry_run=bool(raw.get("dry_run", False)),
            ignore=list(
                raw.get(
                    "ignore",
                    [
                        ".DS_Store",
                        ".*",
                        "*.crdownload",
                        "*.part",
                        "*.download",
                    ],
                )
            ),
            protected_folders=list(protected),
            folders=dict(folders),
            obsidian=dict(raw.get("obsidian") or {}),
        )
