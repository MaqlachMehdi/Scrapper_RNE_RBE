from __future__ import annotations

import datetime
from pathlib import Path

from company_docs_downloader.models import DownloadResult


def write_download_log(
    log_path: Path,
    entry: str,
    company_name: str,
    siren: str | None,
    results: list[DownloadResult],
    error: str | None = None,
) -> None:
    """Ajoute une ligne de log dans le fichier .txt pour une entreprise traitée."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    siren_str = siren or "N/A"

    with log_path.open("a", encoding="utf-8") as f:
        if error:
            f.write(f"[{timestamp}] ERREUR | entree={entry} | entreprise={company_name} | siren={siren_str} | erreur={error}\n")
        else:
            for result in results:
                f.write(
                    f"[{timestamp}] OK | entree={entry} | entreprise={company_name} | siren={siren_str}"
                    f" | document={result.document_type.value} | fichier={result.file_path} | source={result.source}\n"
                )


def build_log_path(output_dir: Path) -> Path:
    """Retourne le chemin du fichier de log dans le dossier de sortie."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"telechargements_{timestamp}.txt"
