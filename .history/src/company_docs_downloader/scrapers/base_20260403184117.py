from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import Browser, Locator, Page, TimeoutError as PlaywrightTimeoutError

from company_docs_downloader.exceptions import DocumentNotFoundError, ScraperError


class BaseScraper:
    def __init__(self, browser: Browser, timeout_ms: int) -> None:
        self.browser = browser
        self.timeout_ms = timeout_ms

    def _goto(self, page: Page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)

    def _quote_query(self, value: str) -> str:
        return quote_plus(value)

    def _wait_for_any(self, candidates: Iterable[Locator], description: str) -> Locator:
        for locator in candidates:
            try:
                locator.first.wait_for(state="visible", timeout=2_000)
                return locator.first
            except PlaywrightTimeoutError:
                continue
        raise DocumentNotFoundError(f"Element introuvable: {description}")

    def _click_any(self, candidates: Iterable[Locator], description: str) -> Locator:
        locator = self._wait_for_any(candidates, description)
        locator.click(timeout=self.timeout_ms)
        return locator

    def _maybe_accept_cookies(self, page: Page) -> None:
        candidates = [
            page.get_by_role("button", name=re.compile(r"(accepter|tout accepter|j'accepte)", re.I)),
            page.get_by_text(re.compile(r"(accepter|tout accepter|j'accepte)", re.I)),
        ]
        for locator in candidates:
            try:
                locator.first.click(timeout=1_500)
                return
            except Exception:
                continue

    def _download_from_locator(self, page: Page, locator: Locator, destination: Path) -> Path:
        href = locator.get_attribute("href")
        if href:
            absolute_url = urljoin(page.url, href)
            response = page.context.request.get(absolute_url, timeout=self.timeout_ms)
            if not response.ok:
                raise ScraperError(f"Echec du telechargement direct depuis {absolute_url}")
            destination.write_bytes(response.body())
            return destination

        with page.expect_download(timeout=self.timeout_ms) as download_info:
            locator.click(timeout=self.timeout_ms)
        download = download_info.value
        download.save_as(str(destination))
        return destination
