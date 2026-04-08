from __future__ import annotations

try:
    import keyring
    from keyring.errors import KeyringError
except ModuleNotFoundError:
    keyring = None

    class KeyringError(Exception):
        pass

from company_docs_downloader.exceptions import ApplicationError
from company_docs_downloader.models import Credentials


SERVICE_NAME = "company-docs-downloader"
USERNAME_ENTRY = "infogreffe.username"
PASSWORD_ENTRY_PREFIX = "infogreffe.password"


def load_infogreffe_credentials() -> Credentials | None:
    if keyring is None:
        return None

    try:
        username = keyring.get_password(SERVICE_NAME, USERNAME_ENTRY)
        if not username:
            return None

        password = keyring.get_password(SERVICE_NAME, _password_entry(username))
        if not password:
            return None

        return Credentials(username=username, password=password)
    except KeyringError as exc:
        raise ApplicationError("Impossible de lire les identifiants Infogreffe depuis le gestionnaire d'identifiants.") from exc


def save_infogreffe_credentials(credentials: Credentials) -> None:
    if keyring is None:
        raise ApplicationError(
            "Le stockage securise des identifiants n'est pas disponible. Installez les dependances du projet avec 'pip install -e .'."
        )

    try:
        previous = keyring.get_password(SERVICE_NAME, USERNAME_ENTRY)
        if previous and previous != credentials.username:
            keyring.delete_password(SERVICE_NAME, _password_entry(previous))
    except Exception:
        pass

    try:
        keyring.set_password(SERVICE_NAME, USERNAME_ENTRY, credentials.username)
        keyring.set_password(SERVICE_NAME, _password_entry(credentials.username), credentials.password)
    except KeyringError as exc:
        raise ApplicationError("Impossible d'enregistrer les identifiants Infogreffe dans le gestionnaire d'identifiants.") from exc


def clear_infogreffe_credentials() -> bool:
    if keyring is None:
        return False

    try:
        username = keyring.get_password(SERVICE_NAME, USERNAME_ENTRY)
        if not username:
            return False

        try:
            keyring.delete_password(SERVICE_NAME, _password_entry(username))
        except Exception:
            pass
        keyring.delete_password(SERVICE_NAME, USERNAME_ENTRY)
        return True
    except KeyringError as exc:
        raise ApplicationError("Impossible de supprimer les identifiants Infogreffe du gestionnaire d'identifiants.") from exc


def _password_entry(username: str) -> str:
    return f"{PASSWORD_ENTRY_PREFIX}:{username}"
