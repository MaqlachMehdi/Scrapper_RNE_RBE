from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import Browser, Frame, Locator, Page, TimeoutError as PlaywrightTimeoutError

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

        login_trigger = self._find_visible_locator(
            page,
            [
                lambda scope: scope.get_by_role("link", name=re.compile(r"(connexion|se connecter)", re.I)),
                lambda scope: scope.get_by_role("button", name=re.compile(r"(connexion|se connecter)", re.I)),
                lambda scope: scope.get_by_text(re.compile(r"(connexion|se connecter)", re.I)),
            ],
            "acces connexion Infogreffe",
        )
        login_trigger.click(timeout=self.timeout_ms)
        self._wait_for_auth_page(page)
        self._wait_for_hydrated_auth_form(page)

        username_input, password_input, submit_button = self._locate_login_form(page)
        self._fill_input(username_input, credentials.username)
        self._fill_input(password_input, credentials.password)
        try:
            username_input.press("Tab", timeout=1_000)
        except Exception:
            pass
        submit_button.click(timeout=self.timeout_ms)
        self._wait_for_login_result(page)

    def _wait_for_auth_page(self, page: Page) -> None:
        try:
            page.wait_for_url(re.compile(r"api\.infogreffe\.fr/.*/openid-connect/auth", re.I), timeout=self.timeout_ms)
            return
        except PlaywrightTimeoutError:
            pass

        try:
            page.wait_for_url(re.compile(r"api\.infogreffe\.fr/.*/login-actions/.*", re.I), timeout=3_000)
            return
        except PlaywrightTimeoutError:
            pass

        form_probe = self._find_visible_locator_in_scopes(page, self._username_locator_builders())
        if form_probe is None:
            raise AuthenticationError("La page d'authentification Infogreffe n'a pas ete ouverte apres le clic sur connexion.")

    def _wait_for_hydrated_auth_form(self, page: Page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

        try:
            page.wait_for_function(
                """
                () => {
                    const bodyText = document.body?.innerText || '';
                    const loginContainer = document.querySelector('.login_form-container');
                    const hasHydratedContainer = Boolean(loginContainer && loginContainer.childElementCount > 0);
                    const hasAuthText = /sign in to your account|email|password|se connecter/i.test(bodyText);
                    const hasInputs = document.querySelectorAll('input, button').length >= 2;
                    return hasHydratedContainer || hasAuthText || hasInputs;
                }
                """,
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(750)

    def _locate_login_form(self, page: Page) -> tuple[Locator, Locator, Locator]:
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while time.monotonic() < deadline:
            for scope in self._iter_scopes(page):
                username_input = self._find_visible_locator_in_scope(scope, self._username_locator_builders())
                password_input = self._find_visible_locator_in_scope(scope, self._password_locator_builders())
                submit_button = self._find_visible_locator_in_scope(scope, self._submit_locator_builders())

                if username_input and password_input and submit_button:
                    return username_input, password_input, submit_button

            page.wait_for_timeout(250)

        raise AuthenticationError("Le formulaire de connexion Infogreffe est introuvable.")

    def _wait_for_login_result(self, page: Page) -> None:
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while time.monotonic() < deadline:
            error_locator = self._find_visible_locator_in_scopes(page, self._error_locator_builders())
            if error_locator is not None:
                message = self._safe_inner_text(error_locator)
                raise AuthenticationError(message or "La connexion Infogreffe a echoue.")

            if self._is_logged_in(page):
                return

            page.wait_for_timeout(250)

        raise AuthenticationError("La connexion Infogreffe n'a pas pu etre confirmee.")

    def _fill_input(self, locator: Locator, value: str) -> None:
        locator.wait_for(state="visible", timeout=self.timeout_ms)
        locator.scroll_into_view_if_needed(timeout=self.timeout_ms)
        locator.click(timeout=self.timeout_ms)

        try:
            locator.clear(timeout=1_500)
        except Exception:
            pass

        try:
            locator.fill(value, timeout=self.timeout_ms)
        except Exception:
            self._force_fill(locator, value)

        current_value = locator.input_value(timeout=1_000)
        if current_value != value:
            try:
                locator.press_sequentially(value, timeout=self.timeout_ms)
            except Exception:
                self._force_fill(locator, value)

        current_value = locator.input_value(timeout=1_000)
        if current_value != value:
            raise AuthenticationError("Le formulaire de connexion Infogreffe refuse la saisie automatique des identifiants.")

    def _force_fill(self, locator: Locator, value: str) -> None:
        locator.evaluate(
            """
            (element, nextValue) => {
                element.focus();
                element.value = nextValue;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                element.dispatchEvent(new Event('blur', { bubbles: true }));
            }
            """,
            [value],
        )

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

    def _iter_scopes(self, page: Page):
        yield page
        for frame in page.frames:
            if frame != page.main_frame:
                yield frame

    def _find_visible_locator(
        self,
        page: Page,
        builders: list[Callable[[Page | Frame], Locator]],
        description: str,
    ) -> Locator:
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while time.monotonic() < deadline:
            locator = self._find_visible_locator_in_scopes(page, builders)
            if locator is not None:
                return locator
            page.wait_for_timeout(250)

        raise DocumentNotFoundError(f"Element introuvable: {description}")

    def _find_visible_locator_in_scopes(
        self,
        page: Page,
        builders: list[Callable[[Page | Frame], Locator]],
    ) -> Locator | None:
        for scope in self._iter_scopes(page):
            locator = self._find_visible_locator_in_scope(scope, builders)
            if locator is not None:
                return locator
        return None

    def _find_visible_locator_in_scope(
        self,
        scope: Page | Frame,
        builders: list[Callable[[Page | Frame], Locator]],
    ) -> Locator | None:
        for builder in builders:
            try:
                locator = builder(scope).first
                locator.wait_for(state="visible", timeout=400)
                return locator
            except Exception:
                continue
        return None

    def _is_logged_in(self, page: Page) -> bool:
        success_builders = [
            lambda scope: scope.get_by_role("link", name=re.compile(r"(deconnexion|se deconnecter|mon compte|mon profil)", re.I)),
            lambda scope: scope.get_by_role("button", name=re.compile(r"(deconnexion|se deconnecter|mon compte|mon profil)", re.I)),
            lambda scope: scope.get_by_text(re.compile(r"(deconnexion|se deconnecter|mon compte|mon profil)", re.I)),
        ]
        if self._find_visible_locator_in_scopes(page, success_builders) is not None:
            return True

        if re.search(r"www\.infogreffe\.fr", page.url, re.I) and not re.search(r"openid-connect|login-actions", page.url, re.I):
            return True

        login_form_still_visible = self._find_visible_locator_in_scopes(
            page,
            self._password_locator_builders() + self._submit_locator_builders(),
        )
        if login_form_still_visible is not None:
            return False

        modal_overlay = self._find_visible_locator_in_scopes(
            page,
            [
                lambda scope: scope.locator("[role='dialog']"),
                lambda scope: scope.locator(".modal, .modal-dialog, .ReactModal__Content"),
            ],
        )
        return modal_overlay is None

    def _username_locator_builders(self) -> list[Callable[[Page | Frame], Locator]]:
        return [
            lambda scope: scope.locator("#username"),
            lambda scope: scope.locator("input[name='username']"),
            lambda scope: scope.locator("input[name='email']"),
            lambda scope: scope.locator("input[name='login']"),
            lambda scope: scope.get_by_label(re.compile(r"(identifiant|adresse e-?mail|email|e-mail)", re.I)),
            lambda scope: scope.get_by_role("textbox", name=re.compile(r"(identifiant|adresse e-?mail|email|e-mail)", re.I)),
            lambda scope: scope.get_by_placeholder(re.compile(r"(identifiant|adresse e-?mail|email|e-mail)", re.I)),
            lambda scope: scope.locator("input[type='email']"),
            lambda scope: scope.locator("input[name*='email' i]"),
            lambda scope: scope.locator("input[id*='email' i]"),
            lambda scope: scope.locator("input[name*='ident' i]"),
            lambda scope: scope.locator("input[id*='ident' i]"),
            lambda scope: scope.locator("input[autocomplete='username']"),
        ]

    def _password_locator_builders(self) -> list[Callable[[Page | Frame], Locator]]:
        return [
            lambda scope: scope.locator("#password"),
            lambda scope: scope.locator("input[name='password']"),
            lambda scope: scope.get_by_label(re.compile(r"mot de passe", re.I)),
            lambda scope: scope.get_by_label(re.compile(r"password", re.I)),
            lambda scope: scope.locator("input[autocomplete='current-password']"),
            lambda scope: scope.get_by_placeholder(re.compile(r"mot de passe", re.I)),
            lambda scope: scope.get_by_placeholder(re.compile(r"password", re.I)),
            lambda scope: scope.locator("input[type='password']"),
            lambda scope: scope.locator("input[name*='password' i]"),
            lambda scope: scope.locator("input[id*='password' i]"),
        ]

    def _submit_locator_builders(self) -> list[Callable[[Page | Frame], Locator]]:
        return [
            lambda scope: scope.locator("#kc-login"),
            lambda scope: scope.get_by_role("button", name=re.compile(r"(connexion|se connecter|valider)", re.I)),
            lambda scope: scope.get_by_role("button", name=re.compile(r"sign in", re.I)),
            lambda scope: scope.locator("button[type='submit']"),
            lambda scope: scope.locator("input[type='submit']"),
        ]

    def _error_locator_builders(self) -> list[Callable[[Page | Frame], Locator]]:
        return [
            lambda scope: scope.locator("[role='alert']").filter(has_text=re.compile(r"(incorrect|invalide|impossible|erreur|bloque|echoue)", re.I)),
            lambda scope: scope.locator(".alert, .alert-danger, .error, .notification-error").filter(
                has_text=re.compile(r"(incorrect|invalide|impossible|erreur|bloque|echoue)", re.I)
            ),
            lambda scope: scope.get_by_text(re.compile(r"(identifiants? incorrects?|mot de passe incorrect|connexion impossible|une erreur est survenue)", re.I)),
        ]

    def _safe_inner_text(self, locator: Locator) -> str | None:
        try:
            return locator.inner_text(timeout=500).strip()
        except Exception:
            return None
