from __future__ import annotations

import re
from pathlib import Path

from company_docs_downloader.models import CompanyIdentity


INVALID_FILENAME_CHARS = re.compile(r"[<>:\"/\\|?*]+")
WHITESPACE = re.compile(r"\s+")
REPEATED_DASHES = re.compile(r"-{2,}")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(value: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("-", value).strip(" .")
    cleaned = WHITESPACE.sub("-", cleaned)
    cleaned = REPEATED_DASHES.sub("-", cleaned)
    return cleaned.strip("-") or "document"


def build_company_output_dir(root: Path, company: CompanyIdentity) -> Path:
    folder_name = sanitize_filename(f"{company.name}-{company.siren or 'unknown'}")
    return ensure_directory(root / folder_name)
