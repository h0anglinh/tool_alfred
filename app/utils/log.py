from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys


@dataclass(frozen=True)
class Logger:
    log_file: Path | None = None

    def _write(self, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {msg}"
        print(line, file=sys.stdout, flush=True)
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.open("a", encoding="utf-8").write(line + "\n")

    def info(self, msg: str) -> None:
        self._write("INFO", msg)

    def warn(self, msg: str) -> None:
        self._write("WARN", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR", msg)