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
            try:
                response = page.context.request.get(absolute_url, timeout=self.timeout_ms)
                if response.ok:
                    destination.write_bytes(response.body())
                    return destination
            except Exception:
                pass

        click_targets = [locator]
        for selector in [
            "xpath=ancestor-or-self::*[self::button or self::a or @role='button' or @role='link'][1]",
            "xpath=ancestor::*[self::button or self::a or @role='button' or @role='link'][1]",
        ]:
            try:
                click_targets.append(locator.locator(selector).first)
            except Exception:
                continue

        try:
            with page.expect_download(timeout=self.timeout_ms) as download_info:
                self._try_click_targets(page, click_targets)
            download = download_info.value
            download.save_as(str(destination))
            return destination
        except PlaywrightTimeoutError as exc:
            if href:
                raise ScraperError(
                    f"Echec du telechargement via requete directe puis via clic navigateur depuis {absolute_url}"
                ) from exc
            raise ScraperError("Le telechargement du document a echoue via le navigateur.") from exc

    def _try_click_targets(self, page: Page, click_targets: list[Locator]) -> None:
        last_error: Exception | None = None
        for target in click_targets:
            try:
                target.wait_for(state="visible", timeout=500)
                target.scroll_into_view_if_needed(timeout=self.timeout_ms)
                target.click(timeout=self.timeout_ms)
                return
            except Exception as exc:
                last_error = exc
            try:
                target.click(timeout=self.timeout_ms, force=True)
                return
            except Exception as exc:
                last_error = exc
            try:
                box = target.bounding_box(timeout=1_000)
                if box:
                    page.mouse.click(box["x"] + (box["width"] / 2), box["y"] + (box["height"] / 2))
                    return
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
