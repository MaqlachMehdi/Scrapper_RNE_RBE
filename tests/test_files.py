from pathlib import Path

from company_docs_downloader.scrapers.base import BaseScraper
from company_docs_downloader.models import CompanyIdentity
from company_docs_downloader.utils.files import build_company_output_dir, sanitize_filename


def test_sanitize_filename_removes_windows_invalid_chars() -> None:
    assert sanitize_filename('SCI F.A.I.T.H. : dossier / 2026') == 'SCI-F.A.I.T.H.-dossier-2026'


def test_build_company_output_dir_uses_company_name_and_siren(tmp_path: Path) -> None:
    identity = CompanyIdentity(name='SCI F.A.I.T.H.', siren='853924389')
    company_dir = build_company_output_dir(tmp_path, identity)
    assert company_dir.exists()
    assert company_dir.name == 'SCI-F.A.I.T.H.-853924389'


class _FakeResponse:
    ok = False


class _FakeRequest:
    def get(self, url: str, timeout: int):
        return _FakeResponse()


class _FakeDownload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def save_as(self, path: str) -> None:
        Path(path).write_bytes(self.payload)


class _FakeDownloadInfo:
    def __init__(self, payload: bytes) -> None:
        self.value = _FakeDownload(payload)


class _FakeExpectDownload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return _FakeDownloadInfo(self.payload)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeContext:
    def __init__(self) -> None:
        self.request = _FakeRequest()


class _FakeLocator:
    def __init__(self, href: str) -> None:
        self.href = href
        self.clicked = False

    def get_attribute(self, name: str):
        if name == 'href':
            return self.href
        return None

    def click(self, timeout: int) -> None:
        self.clicked = True


class _FakePage:
    def __init__(self, payload: bytes) -> None:
        self.url = 'https://www.pappers.fr/entreprise/test'
        self.context = _FakeContext()
        self.payload = payload

    def expect_download(self, timeout: int):
        return _FakeExpectDownload(self.payload)


class _FakeBrowser:
    pass


def test_download_from_locator_falls_back_to_browser_download(tmp_path: Path) -> None:
    scraper = BaseScraper(browser=_FakeBrowser(), timeout_ms=1_000)
    page = _FakePage(payload=b'%PDF-1.4')
    locator = _FakeLocator(href='/export/test.pdf')

    destination = scraper._download_from_locator(page, locator, tmp_path / 'document.pdf')

    assert destination.read_bytes() == b'%PDF-1.4'
    assert locator.clicked is True
