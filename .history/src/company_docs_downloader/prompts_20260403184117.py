from __future__ import annotations

import re
from pathlib import Path

import questionary

from company_docs_downloader.config import AppConfig
from company_docs_downloader.exceptions import ValidationError
from company_docs_downloader.models import CompanyQuery, Credentials, DocumentType, SearchMode, UserRequest


SIREN_PATTERN = re.compile(r"^\d{9}$")


def prompt_user_request(config: AppConfig) -> UserRequest:
    selected_documents = _ask_documents()
    search_mode = _ask_search_mode()
    company_query = _ask_company_query(search_mode)
    output_dir = _ask_output_dir(config.download_root)
    infogreffe_credentials = None

    if DocumentType.STATUTES in selected_documents:
        wants_infogreffe = questionary.confirm(
            "Voulez-vous activer la connexion Infogreffe comme source de repli pour les statuts ?",
            default=True,
        ).ask()
        if wants_infogreffe:
            infogreffe_credentials = _ask_infogreffe_credentials()

    return UserRequest(
        selected_documents=selected_documents,
        company_query=company_query,
        output_dir=output_dir,
        infogreffe_credentials=infogreffe_credentials,
    )


def _ask_documents() -> list[DocumentType]:
    choices = questionary.checkbox(
        "Quels documents voulez-vous telecharger ?",
        choices=[
            questionary.Choice("Extrait INPI / RNE", value=DocumentType.RNE),
            questionary.Choice("Statuts / document juridique pertinent", value=DocumentType.STATUTES),
        ],
        validate=lambda value: True if value else "Selectionnez au moins un document.",
    ).ask()

    if not choices:
        raise ValidationError("Aucun document selectionne.")

    return choices


def _ask_search_mode() -> SearchMode:
    value = questionary.select(
        "Voulez-vous rechercher par nom d'entreprise ou par numero de SIREN ?",
        choices=[
            questionary.Choice("Nom d'entreprise", value=SearchMode.COMPANY_NAME),
            questionary.Choice("Numero de SIREN", value=SearchMode.SIREN),
        ],
    ).ask()

    if value is None:
        raise ValidationError("Mode de recherche non selectionne.")

    return value


def _ask_company_query(search_mode: SearchMode) -> CompanyQuery:
    if search_mode is SearchMode.SIREN:
        value = questionary.text(
            "Entrez le numero de SIREN (9 chiffres) :",
            validate=lambda text: True if SIREN_PATTERN.fullmatch(text or "") else "Le SIREN doit contenir 9 chiffres.",
        ).ask()
    else:
        value = questionary.text(
            "Entrez le nom de l'entreprise :",
            validate=lambda text: True if (text or "").strip() else "Le nom de l'entreprise est obligatoire.",
        ).ask()

    if value is None:
        raise ValidationError("Valeur de recherche manquante.")

    return CompanyQuery(mode=search_mode, value=value.strip())


def _ask_output_dir(default_dir: Path) -> Path:
    raw_path = questionary.text(
        "Dossier de sortie pour les fichiers :",
        default=str(default_dir),
        validate=lambda text: True if (text or "").strip() else "Le dossier de sortie est obligatoire.",
    ).ask()

    if raw_path is None:
        raise ValidationError("Dossier de sortie manquant.")

    return Path(raw_path).expanduser().resolve()


def _ask_infogreffe_credentials() -> Credentials:
    username = questionary.text(
        "Identifiant Infogreffe :",
        validate=lambda text: True if (text or "").strip() else "L'identifiant est obligatoire.",
    ).ask()
    password = questionary.password(
        "Mot de passe Infogreffe :",
        validate=lambda text: True if (text or "").strip() else "Le mot de passe est obligatoire.",
    ).ask()

    if username is None or password is None:
        raise ValidationError("Identifiants Infogreffe incomplets.")

    return Credentials(username=username.strip(), password=password)
