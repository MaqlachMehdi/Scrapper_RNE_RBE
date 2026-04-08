from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from company_docs_downloader.exceptions import DocumentNotFoundError, ScraperError
from company_docs_downloader.models import CompanyIdentity, CompanyQuery, DocumentType, DownloadResult
from company_docs_downloader.scrapers.base import BaseScraper
from company_docs_downloader.utils.files import sanitize_filename


class PappersClient(BaseScraper):
    SEARCH_URL = "https://www.pappers.fr/recherche?q={query}"

    def __init__(self, browser: Browser, timeout_ms: int) -> None:
        super().__init__(browser=browser, timeout_ms=timeout_ms)

    def resolve_company_identity(self, query: CompanyQuery) -> CompanyIdentity:
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            self._open_company_page(page, query)
            heading = self._read_heading(page)
            siren = self._extract_siren(page)
            return CompanyIdentity(name=heading, siren=siren)
        finally:
            context.close()

    def download_rne_extract(self, query: CompanyQuery, output_dir: Path, company: CompanyIdentity) -> DownloadResult:
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            self._open_company_page(page, query)
            self._maybe_accept_cookies(page)
            button = self._wait_for_any(
                [
                    page.get_by_role("button", name=re.compile(r"Extrait INPI", re.I)),
                    page.get_by_role("link", name=re.compile(r"Extrait INPI", re.I)),
                    page.get_by_text(re.compile(r"Extrait INPI", re.I)),
                ],
                "bouton Extrait INPI",
            )
            destination = output_dir / sanitize_filename(f"{company.name}-rne-{company.siren or query.value}.pdf")
            file_path = self._download_from_locator(page, button, destination)
            return DownloadResult(document_type=DocumentType.RNE, source="pappers", file_path=file_path)
        finally:
            context.close()

    def download_latest_statutes(self, query: CompanyQuery, output_dir: Path, company: CompanyIdentity) -> DownloadResult:
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            self._open_company_page(page, query)
            self._maybe_accept_cookies(page)
            self._focus_legal_documents_section(page)
            document_link = self._find_statutes_link(page)
            destination = output_dir / sanitize_filename(f"{company.name}-statuts-{company.siren or query.value}.pdf")
            file_path = self._download_from_locator(page, document_link, destination)
            return DownloadResult(document_type=DocumentType.STATUTES, source="pappers", file_path=file_path)
        finally:
            context.close()

    def _open_company_page(self, page: Page, query: CompanyQuery) -> None:
        self._goto(page, self.SEARCH_URL.format(query=self._quote_query(query.value)))
        self._maybe_accept_cookies(page)

        if "/entreprise/" in page.url:
            return

        result_link = self._wait_for_any(
            [
                page.locator("a[href*='/entreprise/']"),
                page.get_by_role("link").filter(has_text=re.compile(re.escape(query.value), re.I)),
            ],
            "resultat entreprise Pappers",
        )
        result_link.click(timeout=self.timeout_ms)
        try:
            page.wait_for_url(re.compile(r".*/entreprise/.*"), timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise ScraperError("Impossible d'ouvrir la fiche entreprise Pappers.") from exc

    def _read_heading(self, page: Page) -> str:
        candidates = [page.locator("h1"), page.locator("main h1"), page.get_by_role("heading", level=1)]
        heading = self._wait_for_any(candidates, "nom de l'entreprise")
        text = heading.inner_text(timeout=self.timeout_ms).strip()
        return text or "entreprise"

    def _extract_siren(self, page: Page) -> str | None:
        text = page.locator("body").inner_text(timeout=self.timeout_ms)
        match = re.search(r"SIREN\s*:?\s*(\d{3}\s?\d{3}\s?\d{3})", text, re.I)
        if not match:
            return None
        return re.sub(r"\s+", "", match.group(1))

    def _focus_legal_documents_section(self, page: Page) -> None:
        section_title = self._wait_for_any(
            [
                page.get_by_text(re.compile(r"Documents juridiques", re.I)),
                page.get_by_role("heading", name=re.compile(r"Documents juridiques", re.I)),
            ],
            "section Documents juridiques",
        )
        section_title.scroll_into_view_if_needed(timeout=self.timeout_ms)

    def _find_statutes_link(self, page: Page):
        patterns = [
            r"Copie des statuts mis a jour",
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

        raise DocumentNotFoundError("Aucun document de statuts n'a ete trouve sur Pappers.")
