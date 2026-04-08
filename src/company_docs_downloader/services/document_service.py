from __future__ import annotations

from playwright.sync_api import sync_playwright

from company_docs_downloader.config import AppConfig
from company_docs_downloader.exceptions import DocumentNotFoundError, ValidationError
from company_docs_downloader.models import CompanyIdentity, DownloadResult, UserRequest
from company_docs_downloader.models import DocumentType
from company_docs_downloader.scrapers.infogreffe import InfogreffeClient
from company_docs_downloader.scrapers.pappers import PappersClient
from company_docs_downloader.utils.files import build_company_output_dir


class DocumentDownloadService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def execute(self, user_request: UserRequest) -> tuple[CompanyIdentity, list[DownloadResult]]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.headless)
            try:
                pappers = PappersClient(browser=browser, timeout_ms=self.config.timeout_ms)
                company = pappers.resolve_company_identity(user_request.company_query)
                output_dir = build_company_output_dir(user_request.output_dir, company)
                results: list[DownloadResult] = []

                if DocumentType.RNE in user_request.selected_documents:
                    results.append(pappers.download_rne_extract(user_request.company_query, output_dir, company))

                if DocumentType.STATUTES in user_request.selected_documents:
                    results.append(self._download_statutes(user_request, company, output_dir, pappers, browser))

                if DocumentType.RBE in user_request.selected_documents:
                    results.append(self._download_rbe(user_request, company, output_dir, browser))

                return company, results
            finally:
                browser.close()

    def _download_statutes(
        self,
        user_request: UserRequest,
        company: CompanyIdentity,
        output_dir,
        pappers: PappersClient,
        browser,
    ) -> DownloadResult:
        try:
            return pappers.download_latest_statutes(user_request.company_query, output_dir, company)
        except DocumentNotFoundError:
            if user_request.infogreffe_credentials is None:
                raise

        infogreffe = InfogreffeClient(
            browser=browser,
            timeout_ms=self.config.timeout_ms,
            allow_manual_login=self.config.allow_manual_infogreffe_login,
        )
        return infogreffe.download_latest_statutes(
            user_request.company_query,
            user_request.infogreffe_credentials,
            output_dir,
            company,
        )

    def _download_rbe(self, user_request: UserRequest, company: CompanyIdentity, output_dir, browser) -> DownloadResult:
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
        )
