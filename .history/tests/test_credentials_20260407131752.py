from company_docs_downloader.models import Credentials
from company_docs_downloader.utils import credentials as credentials_module


def test_save_and_load_infogreffe_credentials(monkeypatch) -> None:
    store: dict[tuple[str, str], str] = {}

    def fake_get_password(service: str, username: str):
        return store.get((service, username))

    def fake_set_password(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    def fake_delete_password(service: str, username: str) -> None:
        store.pop((service, username), None)

    monkeypatch.setattr(credentials_module.keyring, "get_password", fake_get_password)
    monkeypatch.setattr(credentials_module.keyring, "set_password", fake_set_password)
    monkeypatch.setattr(credentials_module.keyring, "delete_password", fake_delete_password)

    credentials = Credentials(username="user@example.com", password="secret")
    credentials_module.save_infogreffe_credentials(credentials)

    loaded = credentials_module.load_infogreffe_credentials()

    assert loaded == credentials


def test_clear_infogreffe_credentials(monkeypatch) -> None:
    store = {
        (credentials_module.SERVICE_NAME, credentials_module.USERNAME_ENTRY): "user@example.com",
        (credentials_module.SERVICE_NAME, f"{credentials_module.PASSWORD_ENTRY_PREFIX}:user@example.com"): "secret",
    }

    def fake_get_password(service: str, username: str):
        return store.get((service, username))

    def fake_delete_password(service: str, username: str) -> None:
        store.pop((service, username), None)

    monkeypatch.setattr(credentials_module.keyring, "get_password", fake_get_password)
    monkeypatch.setattr(credentials_module.keyring, "delete_password", fake_delete_password)

    removed = credentials_module.clear_infogreffe_credentials()

    assert removed is True
    assert store == {}