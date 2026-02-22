from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureContext:
    config: dict[str, Any]


class Feature(abc.ABC):
    key: str

    @abc.abstractmethod
    def run_forever(self, ctx: FeatureContext) -> None:
        raise NotImplementedError