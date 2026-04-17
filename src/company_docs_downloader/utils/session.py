from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from company_docs_downloader.exceptions import ApplicationError


def get_session_path() -> Path:
    """Retourne le chemin du fichier de session Infogreffe."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    directory = base / "company-docs-downloader"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "infogreffe_session.json"


def session_exists() -> bool:
    """Retourne True si un fichier de session sauvegardé existe."""
    return get_session_path().exists()


def save_session_state(storage_state: dict) -> None:
    """Sauvegarde l'état de session Playwright dans un fichier protégé."""
    path = get_session_path()
    try:
        path.write_text(json.dumps(storage_state), encoding="utf-8")
        _restrict_permissions(path)
    except OSError as exc:
        raise ApplicationError(f"Impossible de sauvegarder la session Infogreffe : {exc}") from exc


def load_session_path() -> Path | None:
    """Retourne le chemin vers la session si elle existe, sinon None."""
    path = get_session_path()
    if path.exists():
        return path
    return None


def clear_session_state() -> bool:
    """Supprime la session sauvegardée. Retourne True si un fichier existait."""
    path = get_session_path()
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError as exc:
            raise ApplicationError(f"Impossible de supprimer la session Infogreffe : {exc}") from exc
    return False


def _restrict_permissions(path: Path) -> None:
    """Restreint le fichier en lecture/écriture pour le propriétaire uniquement."""
    if sys.platform == "win32":
        _restrict_permissions_windows(path)
    else:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _restrict_permissions_windows(path: Path) -> None:
    """Sur Windows, supprime l'héritage de droits et n'autorise que l'utilisateur courant."""
    try:
        import win32security  # type: ignore[import]
        import ntsecuritycon as con  # type: ignore[import]

        sd = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
        user_sid, _, _ = win32security.LookupAccountName(None, os.getlogin())
        dacl = win32security.ACL()
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_GENERIC_READ | con.FILE_GENERIC_WRITE, user_sid)
        sd.SetSecurityDescriptorDacl(True, dacl, False)
        win32security.SetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION, sd)
    except Exception:
        # pywin32 non disponible : on ignore silencieusement.
        # Le fichier reste protégé par les droits du répertoire APPDATA.
        pass
