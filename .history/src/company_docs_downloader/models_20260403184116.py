from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DocumentType(str, Enum):
    RNE = "rne"
    STATUTES = "statutes"


class SearchMode(str, Enum):
    COMPANY_NAME = "company_name"
    SIREN = "siren"


@dataclass(slots=True)
class CompanyQuery:
    mode: SearchMode
    value: str


@dataclass(slots=True)
class Credentials:
    username: str
    password: str


@dataclass(slots=True)
class CompanyIdentity:
    name: str
    siren: str | None = None


@dataclass(slots=True)
class UserRequest:
    selected_documents: list[DocumentType]
    company_query: CompanyQuery
    output_dir: Path
    infogreffe_credentials: Credentials | None = None


@dataclass(slots=True)
class DownloadResult:
    document_type: DocumentType
    source: str
    file_path: Path
