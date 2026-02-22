from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.features.base import Feature, FeatureContext
from app.utils.log import Logger
from app.utils.obsidian import format_section, replace_markdown, resolve_target_from_config


@dataclass(frozen=True)
class DevGitOverviewSettings:
    root: Path
    scan_interval_seconds: int
    max_depth: int
    ignore_dirs: list[str]
    obsidian: dict[str, Any]


@dataclass(frozen=True)
class RepoStatus:
    project: str
    branch: str
    last_push: str
    last_push_at: datetime | None
    dirty_count: int


class DevGitOverview(Feature):
    key = "dev_git_overview"

    def run_forever(self, ctx: FeatureContext) -> None:
        cfg = self._load_settings(ctx.config.get(self.key, {}))
        logger = Logger(log_file=Path("/logs/alfred.log"))
        logger.info(f"Dev Git Overview started (root={cfg.root}, interval={cfg.scan_interval_seconds}s)")

        while True:
            self._scan_once(cfg, logger)
            time.sleep(cfg.scan_interval_seconds)

    def _scan_once(self, cfg: DevGitOverviewSettings, logger: Logger) -> None:
        if not cfg.root.exists():
            logger.error(f"Dev Git Overview root does not exist: {cfg.root}")
            return

        repos = self._discover_repositories(cfg)
        statuses: list[RepoStatus] = []

        for repo_path in repos:
            status = self._inspect_repo(repo_path)
            if status is not None:
                statuses.append(status)

        statuses.sort(key=lambda item: item.project.lower())
        logger.info(f"Dev Git Overview scan done: repos={len(statuses)}")
        self._maybe_write_obsidian(cfg, statuses, logger)

    def _discover_repositories(self, cfg: DevGitOverviewSettings) -> list[Path]:
        root = cfg.root
        root_depth = len(root.parts)
        repos: list[Path] = []

        for dirpath, dirnames, _filenames in os.walk(root):
            current = Path(dirpath)
            depth = len(current.parts) - root_depth

            if cfg.max_depth >= 0 and depth > cfg.max_depth:
                dirnames[:] = []
                continue

            if ".git" in dirnames:
                repos.append(current)
                dirnames[:] = []
                continue

            dirnames[:] = [name for name in dirnames if name not in cfg.ignore_dirs]

        return repos

    def _inspect_repo(self, repo_path: Path) -> RepoStatus | None:
        branch = self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        if branch is None:
            return None

        status_output = self._run_git(repo_path, ["status", "--porcelain"])
        dirty_count = len([line for line in (status_output or "").splitlines() if line.strip()])

        last_push, last_push_at = self._resolve_last_push(repo_path)

        return RepoStatus(
            project=repo_path.name,
            branch=branch,
            last_push=last_push,
            last_push_at=last_push_at,
            dirty_count=dirty_count,
        )

    def _resolve_last_push(self, repo_path: Path) -> tuple[str, datetime | None]:
        upstream = self._run_git(
            repo_path,
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        )
        if upstream is None:
            return "no upstream", None

        reflog = self._run_git(
            repo_path,
            ["reflog", "show", "--date=iso-strict", "--format=%cd|%gs", upstream, "-n", "100"],
        )
        if reflog:
            for line in reflog.splitlines():
                if "|" not in line:
                    continue
                when, message = line.split("|", 1)
                if "update by push" in message.lower():
                    return when, self._parse_git_datetime(when)

        upstream_commit_date = self._run_git(
            repo_path,
            ["log", "-1", "--date=iso-strict", "--format=%cd", "@{u}"],
        )
        if upstream_commit_date:
            return upstream_commit_date, self._parse_git_datetime(upstream_commit_date)

        return "unknown", None

    def _run_git(self, repo_path: Path, args: list[str]) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_path), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def _parse_git_datetime(self, value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _maybe_write_obsidian(
        self,
        cfg: DevGitOverviewSettings,
        statuses: list[RepoStatus],
        logger: Logger,
    ) -> None:
        obs = cfg.obsidian or {}
        if not bool(obs.get("enabled", False)):
            return

        target = resolve_target_from_config(obs, default_filename=f"{self.key}.md")
        if target is None:
            logger.error("Obsidian enabled but missing obsidian.vault_path and note path settings")
            return

        title = str(obs.get("title", "Alfred • Dev Git Overview"))
        lines = self._build_table_lines(statuses)
        markdown = format_section(title, lines)

        try:
            note_path = replace_markdown(target, markdown)
            logger.info(f"WROTE obsidian note: {note_path}")
        except Exception as e:
            logger.error(f"FAILED writing Obsidian note: {e}")

    def _build_table_lines(self, statuses: list[RepoStatus]) -> list[str]:
        lines: list[str] = [
            "| Project | Branch | Last Push | Uncommitted Changes | Flag |",
            "|---|---|---|---|---|",
        ]
        if not statuses:
            lines.append("| - | - | - | - | - |")
            return lines

        now_utc = datetime.now(timezone.utc)
        for status in statuses:
            uncommitted = "no"
            if status.dirty_count > 0:
                uncommitted = f"yes ({status.dirty_count})"
            flags = self._build_flags(status, now_utc)

            lines.append(
                "| "
                f"{self._md_cell(f'[[{status.project}]]')} | "
                f"{self._md_cell(status.branch)} | "
                f"{self._md_cell(status.last_push)} | "
                f"{self._md_cell(uncommitted)} | "
                f"{self._md_cell(flags)} |"
            )
        return lines

    def _build_flags(self, status: RepoStatus, now_utc: datetime) -> str:
        if status.last_push_at is None:
            return "-"

        age = now_utc - status.last_push_at.astimezone(timezone.utc)
        flags: list[str] = []

        if age > timedelta(days=7):
            flags.append("stale>7d")
        if age > timedelta(hours=24) and status.dirty_count > 0:
            flags.append("dirty+24h")

        return ", ".join(flags) if flags else "-"

    def _md_cell(self, value: str) -> str:
        return value.replace("|", "\\|").strip() or "-"

    def _load_settings(self, raw: dict[str, Any]) -> DevGitOverviewSettings:
        return DevGitOverviewSettings(
            root=Path(str(raw.get("root", "/dev_projects"))),
            scan_interval_seconds=int(raw.get("scan_interval_seconds", 900)),
            max_depth=int(raw.get("max_depth", 6)),
            ignore_dirs=list(raw.get("ignore_dirs", ["node_modules", ".venv", "venv", "__pycache__"])),
            obsidian=dict(raw.get("obsidian") or {}),
        )
