from __future__ import annotations

import questionary

from company_docs_downloader.exceptions import ApplicationError, ValidationError
from company_docs_downloader.models import Credentials
from company_docs_downloader.utils.credentials import clear_infogreffe_credentials, load_infogreffe_credentials, save_infogreffe_credentials


def configure_main() -> int:
    try:
        current = load_infogreffe_credentials()
        if current is not None:
            print(f"Identifiants Infogreffe deja enregistres pour: {current.username}")
            replace = questionary.confirm("Voulez-vous les remplacer ?", default=False).ask()
            if not replace:
                return 0

        credentials = _prompt_credentials()
        save_infogreffe_credentials(credentials)
    except KeyboardInterrupt:
        print("Operation annulee par l'utilisateur.")
        return 130
    except ApplicationError as exc:
        print(f"Erreur: {exc}")
        return 1

    print("Identifiants Infogreffe enregistres dans le gestionnaire d'identifiants Windows.")
    return 0


def clear_main() -> int:
    try:
        removed = clear_infogreffe_credentials()
    except ApplicationError as exc:
        print(f"Erreur: {exc}")
        return 1

    if removed:
        print("Identifiants Infogreffe supprimes du gestionnaire d'identifiants Windows.")
    else:
        print("Aucun identifiant Infogreffe enregistre.")
    return 0


def _prompt_credentials() -> Credentials:
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
