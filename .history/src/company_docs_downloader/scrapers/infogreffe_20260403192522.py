from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from company_docs_downloader.exceptions import AuthenticationError, DocumentNotFoundError, ScraperError
from company_docs_downloader.models import CompanyIdentity, CompanyQuery, Credentials, DocumentType, DownloadResult
from company_docs_downloader.scrapers.base import BaseScraper
from company_docs_downloader.utils.files import sanitize_filename


class InfogreffeClient(BaseScraper):
    HOME_URL = "https://www.infogreffe.fr/"

    def __init__(self, browser: Browser, timeout_ms: int) -> None:
        super().__init__(browser=browser, timeout_ms=timeout_ms)

    def download_latest_statutes(
        self,
        query: CompanyQuery,
        credentials: Credentials,
        output_dir: Path,
        company: CompanyIdentity,
    ) -> DownloadResult:
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            self._login(page, credentials)
            self._open_company_page(page, query)
            self._open_documents_tab(page)
            document_link = self._find_statutes_link(page)
            destination = output_dir / sanitize_filename(f"{company.name}-statuts-infogreffe-{company.siren or query.value}.pdf")
            file_path = self._download_from_locator(page, document_link, destination)
            return DownloadResult(document_type=DocumentType.STATUTES, source="infogreffe", file_path=file_path)
        finally:
            context.close()

    def download_rbe(
        self,
        query: CompanyQuery,
        credentials: Credentials,
        output_dir: Path,
        company: CompanyIdentity,
    ) -> DownloadResult:
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            self._login(page, credentials)
            self._open_company_page(page, query)
            self._open_beneficial_owners_tab(page)
            document_link = self._find_rbe_download(page)
            destination = output_dir / sanitize_filename(f"{company.name}-rbe-{company.siren or query.value}.pdf")
            file_path = self._download_from_locator(page, document_link, destination)
            return DownloadResult(document_type=DocumentType.RBE, source="infogreffe", file_path=file_path)
        finally:
            context.close()

    def _login(self, page: Page, credentials: Credentials) -> None:
        self._goto(page, self.HOME_URL)
        self._maybe_accept_cookies(page)

        login_trigger = self._wait_for_any(
            [
                page.get_by_role("link", name=re.compile(r"(connexion|se connecter)", re.I)),
                page.get_by_role("button", name=re.compile(r"(connexion|se connecter)", re.I)),
            ],
            "acces connexion Infogreffe",
        )
        login_trigger.click(timeout=self.timeout_ms)

        username_input = self._wait_for_any(
            [
                page.locator("input[type='email']"),
                page.locator("input[name*='email' i]"),
                page.locator("input[name*='ident' i]"),
                page.locator("input[id*='email' i]"),
            ],
            "champ identifiant Infogreffe",
        )
        password_input = self._wait_for_any(
            [
                page.locator("input[type='password']"),
                page.locator("input[name*='password' i]"),
            ],
            "champ mot de passe Infogreffe",
        )

        username_input.fill(credentials.username, timeout=self.timeout_ms)
        password_input.fill(credentials.password, timeout=self.timeout_ms)

        submit_button = self._wait_for_any(
            [
                page.get_by_role("button", name=re.compile(r"(connexion|se connecter|valider)", re.I)),
                page.locator("button[type='submit']"),
            ],
            "bouton de connexion Infogreffe",
        )
        submit_button.click(timeout=self.timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

        error_banner = page.get_by_text(re.compile(r"(identifiant|mot de passe|connexion impossible|erreur)", re.I))
        try:
            error_banner.first.wait_for(state="visible", timeout=1_500)
            raise AuthenticationError("La connexion Infogreffe a echoue.")
        except PlaywrightTimeoutError:
            return

    def _open_company_page(self, page: Page, query: CompanyQuery) -> None:
        search_input = self._wait_for_any(
            [
                page.locator("input[placeholder*='Rechercher une entreprise' i]"),
                page.locator("input[type='search']"),
                page.locator("input[name*='search' i]"),
            ],
            "champ de recherche Infogreffe",
        )
        search_input.fill(query.value, timeout=self.timeout_ms)
        search_input.press("Enter", timeout=self.timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

        if re.search(r"(entreprise|societe)", page.url, re.I):
            return

        result_link = self._wait_for_any(
            [
                page.locator("a[href*='entreprise']"),
                page.locator("a[href*='societe']"),
                page.get_by_role("link").filter(has_text=re.compile(re.escape(query.value), re.I)),
            ],
            "resultat entreprise Infogreffe",
        )
        result_link.click(timeout=self.timeout_ms)

    def _open_documents_tab(self, page: Page) -> None:
        documents_tab = self._wait_for_any(
            [
                page.get_by_role("tab", name=re.compile(r"Documents", re.I)),
                page.get_by_role("link", name=re.compile(r"Documents", re.I)),
                page.get_by_text(re.compile(r"Documents", re.I)),
            ],
            "onglet Documents Infogreffe",
        )
        documents_tab.click(timeout=self.timeout_ms)

    def _open_beneficial_owners_tab(self, page: Page) -> None:
        tab = self._wait_for_any(
            [
                page.get_by_role("tab", name=re.compile(r"Beneficiaires? effectifs?", re.I)),
                page.get_by_role("link", name=re.compile(r"Beneficiaires? effectifs?", re.I)),
                page.get_by_text(re.compile(r"Beneficiaires? effectifs?", re.I)),
            ],
            "onglet Beneficiaires effectifs Infogreffe",
        )
        tab.click(timeout=self.timeout_ms)

    def _find_rbe_download(self, page: Page):
        candidates = [
            page.get_by_role("button", name=re.compile(r"copie integrale.*assujettis", re.I)),
            page.get_by_role("link", name=re.compile(r"copie integrale.*assujettis", re.I)),
            page.get_by_text(re.compile(r"copie integrale.*assujettis", re.I)),
            page.get_by_role("button", name=re.compile(r"beneficiaires effectifs", re.I)),
            page.get_by_role("link", name=re.compile(r"beneficiaires effectifs", re.I)),
        ]
        return self._wait_for_any(candidates, "telechargement RBE Infogreffe")

    def _find_statutes_link(self, page: Page):
        patterns = [
            r"Copie des statuts",
            r"Statuts mis a jour",
            r"statuts",
        ]
        for pattern in patterns:
            rows = page.locator("div, li, tr").filter(has_text=re.compile(pattern, re.I))
            row_count = min(rows.count(), 8)
            for index in range(row_count):
                row = rows.nth(index)
                links = row.locator("a[href]")
                if links.count() > 0:
                    return links.last
                buttons = row.get_by_role("button")
                if buttons.count() > 0:
                    return buttons.last

        raise DocumentNotFoundError("Aucun document de statuts n'a ete trouve sur Infogreffe.")
