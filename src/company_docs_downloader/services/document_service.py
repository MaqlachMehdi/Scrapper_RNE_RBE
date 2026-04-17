from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

from company_docs_downloader.config import AppConfig
from company_docs_downloader.exceptions import ValidationError
from company_docs_downloader.models import BatchRequest, CompanyIdentity, DownloadResult, UserRequest
from company_docs_downloader.models import CompanyQuery, DocumentType, SearchMode
from company_docs_downloader.scrapers.infogreffe import InfogreffeClient
from company_docs_downloader.scrapers.pappers import PappersClient
from company_docs_downloader.utils.files import build_company_output_dir


SIREN_PATTERN = re.compile(r"^\d{9}$")


class DocumentDownloadService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def execute(self, user_request: UserRequest, force_infogreffe_login: bool = False) -> tuple[CompanyIdentity, list[DownloadResult]]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.headless)
            try:
                pappers = PappersClient(browser=browser, timeout_ms=self.config.timeout_ms)
                company = pappers.resolve_company_identity(user_request.company_query)
                output_dir = build_company_output_dir(user_request.output_dir, company)
                results: list[DownloadResult] = []

                if DocumentType.RNE in user_request.selected_documents:
                    results.append(pappers.download_rne_extract(user_request.company_query, output_dir, company))

                if DocumentType.RBE in user_request.selected_documents:
                    results.append(self._download_rbe(user_request, company, output_dir, browser, force_login=force_infogreffe_login))

                return company, results
            finally:
                browser.close()

    def execute_batch_entry(self, batch_request: BatchRequest, entry: str, force_login: bool = False) -> tuple[CompanyIdentity, list[DownloadResult]]:
        """Traite une entreprise depuis une entrée batch (nom ou SIREN)."""
        if SIREN_PATTERN.fullmatch(entry):
            query = CompanyQuery(mode=SearchMode.SIREN, value=entry)
        else:
            query = CompanyQuery(mode=SearchMode.COMPANY_NAME, value=entry)

        user_request = UserRequest(
            selected_documents=batch_request.selected_documents,
            company_query=query,
            output_dir=batch_request.output_dir,
            infogreffe_credentials=batch_request.infogreffe_credentials,
        )
        return self.execute(user_request, force_infogreffe_login=force_login)

    def _download_rbe(self, user_request: UserRequest, company: CompanyIdentity, output_dir, browser, force_login: bool = False) -> DownloadResult:
        if user_request.infogreffe_credentials is None:
            raise ValidationError("Le telechargement du RBE requiert des identifiants Infogreffe.")

        infogreffe = InfogreffeClient(
            browser=browser,
            timeout_ms=self.config.timeout_ms,
            allow_manual_login=self.config.allow_manual_infogreffe_login,
        )
        return infogreffe.download_rbe(
            user_request.company_query,
            user_request.infogreffe_credentials,
            output_dir,
            company,
            force_login=force_login,
        )
