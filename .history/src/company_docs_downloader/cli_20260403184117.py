from __future__ import annotations

from pathlib import Path

from company_docs_downloader.config import AppConfig
from company_docs_downloader.exceptions import ApplicationError
from company_docs_downloader.prompts import prompt_user_request
from company_docs_downloader.services.document_service import DocumentDownloadService
from company_docs_downloader.utils.files import ensure_directory


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    config = AppConfig.from_project_root(project_root)
    ensure_directory(config.download_root)

    try:
        user_request = prompt_user_request(config)
        ensure_directory(user_request.output_dir)
        service = DocumentDownloadService(config)
        company, results = service.execute(user_request)
    except KeyboardInterrupt:
        print("Operation annulee par l'utilisateur.")
        return 130
    except ApplicationError as exc:
        print(f"Erreur: {exc}")
        return 1

    print(f"Entreprise: {company.name} ({company.siren or 'SIREN non detecte'})")
    for result in results:
        print(f"- {result.document_type.value}: {result.file_path} [source={result.source}]")
    return 0
