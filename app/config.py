from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import yaml


@dataclass(frozen=True)
class AppConfig:
    enabled_features: list[str]
    feature_config: dict[str, Any]
    logs_dir: Path

    @staticmethod
    def load() -> "AppConfig":
        path = Path(os.environ.get("CONFIG_PATH", "/config/alfred.yml"))
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        enabled = raw.get("enabled_features", [])
        feature_cfg = raw.get("features", {})
        logs_dir = Path(raw.get("logs_dir", "/logs"))

        return AppConfig(
            enabled_features=list(enabled),
            feature_config=dict(feature_cfg),
            logs_dir=logs_dir,
        )