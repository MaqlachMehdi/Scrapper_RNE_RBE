from __future__ import annotations

import sys
from pathlib import Path

from tqdm import tqdm

from company_docs_downloader.config import AppConfig
from company_docs_downloader.exceptions import ApplicationError
from company_docs_downloader.prompts import prompt_batch_request, prompt_mode, prompt_user_request
from company_docs_downloader.services.document_service import DocumentDownloadService
from company_docs_downloader.utils.files import ensure_directory
from company_docs_downloader.utils.logger import build_log_path, write_download_log
from company_docs_downloader.utils.session import clear_session_state


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]

    args = sys.argv[1:]
    headless = "--headless" in args

    config = AppConfig.from_project_root(project_root)
    config = AppConfig(
        project_root=config.project_root,
        download_root=config.download_root,
        headless=headless,
        timeout_ms=config.timeout_ms,
        allow_manual_infogreffe_login=config.allow_manual_infogreffe_login,
    )
    ensure_directory(config.download_root)

    try:
        mode, batch_file = prompt_mode(config.download_root)
    except KeyboardInterrupt:
        print("Operation annulee par l'utilisateur.")
        return 130
    except ApplicationError as exc:
        print(f"Erreur: {exc}")
        return 1

    if mode == "batch":
        return _run_batch(config, batch_file)
    return _run_single(config)


def _run_single(config: AppConfig) -> int:
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


def _run_batch(config: AppConfig, input_file: Path) -> int:
    if not input_file.exists():
        print(f"Erreur: fichier introuvable : {input_file}")
        return 1

    lines = [l.strip() for l in input_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        print("Erreur: le fichier ne contient aucune entree valide.")
        return 1

    try:
        batch_request = prompt_batch_request(config)
    except KeyboardInterrupt:
        print("Operation annulee par l'utilisateur.")
        return 130
    except ApplicationError as exc:
        print(f"Erreur: {exc}")
        return 1

    ensure_directory(batch_request.output_dir)
    log_path = build_log_path(batch_request.output_dir)
    print(f"Log de telechargement : {log_path}\n")

    # Forcer un login frais a chaque lancement de batch
    clear_session_state()

    service = DocumentDownloadService(config)
    has_error = False

    with tqdm(lines, desc="Entreprises", unit="entreprise", dynamic_ncols=True) as progress:
        for idx, entry in enumerate(progress):
            progress.set_postfix_str(entry[:40])
            try:
                force_login = (idx == 0)
                company, results = service.execute_batch_entry(batch_request, entry, force_login=force_login)
                tqdm.write(f"[OK] {company.name} ({company.siren or 'N/A'})")
                for result in results:
                    tqdm.write(f"     - {result.document_type.value}: {result.file_path}")
                write_download_log(log_path, entry, company.name, company.siren, results)
            except ApplicationError as exc:
                tqdm.write(f"[ERREUR] '{entry}': {exc}")
                write_download_log(log_path, entry, entry, None, [], error=str(exc))
                has_error = True
            except KeyboardInterrupt:
                print("\nOperation annulee par l'utilisateur.")
                return 130

    print(f"\nTermine. Log sauvegarde : {log_path}")
    return 1 if has_error else 0
