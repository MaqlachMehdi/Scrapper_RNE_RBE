from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    project_root: Path
    download_root: Path
    headless: bool = False
    timeout_ms: int = 20_000

    @classmethod
    def from_project_root(cls, project_root: Path) -> "AppConfig":
        download_root = project_root / "downloads"
        return cls(project_root=project_root, download_root=download_root)
