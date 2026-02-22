from __future__ import annotations

from typing import Dict, Type

from app.features.base import Feature
from app.features.dev_git_overview import DevGitOverview
from app.features.download_janitor import DownloadsJanitor

FEATURES: Dict[str, Type[Feature]] = {
    DownloadsJanitor.key: DownloadsJanitor,
    DevGitOverview.key: DevGitOverview,
}
