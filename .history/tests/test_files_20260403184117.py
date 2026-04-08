from pathlib import Path

from company_docs_downloader.models import CompanyIdentity
from company_docs_downloader.utils.files import build_company_output_dir, sanitize_filename


def test_sanitize_filename_removes_windows_invalid_chars() -> None:
    assert sanitize_filename('SCI F.A.I.T.H. : dossier / 2026') == 'SCI-F.A.I.T.H.-dossier---2026'


def test_build_company_output_dir_uses_company_name_and_siren(tmp_path: Path) -> None:
    identity = CompanyIdentity(name='SCI F.A.I.T.H.', siren='853924389')
    company_dir = build_company_output_dir(tmp_path, identity)
    assert company_dir.exists()
    assert company_dir.name == 'SCI-F.A.I.T.H.-853924389'
