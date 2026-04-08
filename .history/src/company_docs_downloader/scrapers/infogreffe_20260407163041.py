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

    def __init__(self, browser: Browser, timeout_ms: int, allow_manual_login: bool = True) -> None:
        super().__init__(browser=browser, timeout_ms=timeout_ms)
        self.allow_manual_login = allow_manual_login

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
            self._open_company_page(page, query, company)
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
            self._open_company_page(page, query, company)
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

        if self._is_cloudflare_block(page):
            if self._try_manual_login(page, "Infogreffe a bloque la navigation automatisee via Cloudflare."):
                return
            raise AuthenticationError("Infogreffe a bloque la navigation automatisee via Cloudflare.")

        try:
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

            if self._is_cloudflare_block(page):
                raise AuthenticationError("Infogreffe a presente une page de blocage Cloudflare pendant l'authentification.")

            username_input, password_input, submit_button = self._locate_login_form(page)
            self._fill_input(username_input, credentials.username)
            self._fill_input(password_input, credentials.password)
            try:
                username_input.press("Tab", timeout=1_000)
            except Exception:
                pass
            submit_button.click(timeout=self.timeout_ms)
            self._wait_for_login_result(page)
            self._handle_post_login_pages(page)
        except AuthenticationError as exc:
            if self._try_manual_login(page, str(exc)):
                return
            raise

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
            if self._is_cloudflare_block(page):
                raise AuthenticationError("Infogreffe a affiche une page de blocage Cloudflare apres la tentative de connexion.")

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

    def _open_company_page(self, page: Page, query: CompanyQuery, company: CompanyIdentity | None = None) -> None:
        self._handle_post_login_pages(page)

        search_value = company.siren if company and company.siren else query.value
        search_input = self._wait_for_any(
            [
                page.locator("input[placeholder*='Rechercher une entreprise' i]"),
                page.locator("input[type='search']"),
                page.locator("input[name*='search' i]"),
            ],
            "champ de recherche Infogreffe",
        )
        search_input.fill(search_value, timeout=self.timeout_ms)
        search_input.press("Enter", timeout=self.timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

        if self._is_company_profile_page(page) and not self._has_search_results(page):
            return

        result_link = self._find_company_result(page, query, company, search_value)
        result_link.scroll_into_view_if_needed(timeout=self.timeout_ms)
        result_link.click(timeout=self.timeout_ms)
        self._wait_for_company_profile_page(page)

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
        if self._find_visible_locator_in_scopes(page, self._rbe_download_locator_builders()) is not None:
            return

        tab = self._wait_for_any(
            [
                page.get_by_role("tab", name=re.compile(r"B[ée]n[ée]ficiaires? effectifs?", re.I)),
                page.get_by_role("link", name=re.compile(r"B[ée]n[ée]ficiaires? effectifs?", re.I)),
                page.get_by_text(re.compile(r"B[ée]n[ée]ficiaires? effectifs?", re.I)),
                page.get_by_role("tab", name=re.compile(r"b[ée]n[ée]ficiaire", re.I)),
                page.get_by_role("link", name=re.compile(r"b[ée]n[ée]ficiaire", re.I)),
            ],
            "onglet Beneficiaires effectifs Infogreffe",
        )
        tab.scroll_into_view_if_needed(timeout=self.timeout_ms)
        tab.click(timeout=self.timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

    def _find_rbe_download(self, page: Page):
        return self._wait_for_any(self._rbe_download_locator_builders(page), "telechargement RBE Infogreffe")

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

    def _wait_for_company_profile_page(self, page: Page) -> None:
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while time.monotonic() < deadline:
            if self._is_company_profile_page(page) and not self._has_search_results(page):
                return
            page.wait_for_timeout(250)

        raise DocumentNotFoundError("La fiche entreprise Infogreffe n'a pas ete ouverte.")

    def _is_company_profile_page(self, page: Page) -> bool:
        if re.search(r"/(entreprise|societe)/[^/?#]+", page.url, re.I):
            return True

        profile_markers = [
            lambda scope: scope.get_by_role("tab", name=re.compile(r"Documents|Dirigeants|Etablissements|B[ée]n[ée]ficiaires? effectifs?", re.I)),
            lambda scope: scope.get_by_role("link", name=re.compile(r"Documents|Dirigeants|Etablissements|B[ée]n[ée]ficiaires? effectifs?", re.I)),
            lambda scope: scope.get_by_text(re.compile(r"Documents|Dirigeants|Etablissements|B[ée]n[ée]ficiaires? effectifs?", re.I)),
        ]
        return self._find_visible_locator_in_scopes(page, profile_markers) is not None

    def _has_search_results(self, page: Page) -> bool:
        result_builders = self._result_locator_builders(None, None, None)
        return self._find_visible_locator_in_scopes(page, result_builders) is not None

    def _find_company_result(
        self,
        page: Page,
        query: CompanyQuery,
        company: CompanyIdentity | None,
        search_value: str,
    ) -> Locator:
        card_patterns = [candidate for candidate in [search_value, query.value, company.name if company else None] if candidate]

        for candidate in card_patterns:
            escaped = re.escape(candidate)
            cards = page.locator("div, li, article, tr, section").filter(has_text=re.compile(escaped, re.I))
            try:
                count = min(cards.count(), 10)
            except Exception:
                count = 0
            for index in range(count):
                card = cards.nth(index)
                for selector in ["a[href*='entreprise']", "a[href*='societe']", "a[href*='fiche']"]:
                    try:
                        link = card.locator(selector).first
                        link.wait_for(state="visible", timeout=400)
                        return link
                    except Exception:
                        continue

        builders = self._result_locator_builders(search_value, query.value, company.name if company else None)
        return self._find_visible_locator(page, builders, "resultat entreprise Infogreffe")

    def _result_locator_builders(
        self,
        search_value: str | None,
        raw_query: str | None,
        company_name: str | None,
    ) -> list[Callable[[Page | Frame], Locator]]:
        href_matchers = ["a[href*='entreprise']", "a[href*='societe']", "a[href*='fiche']"]
        builders: list[Callable[[Page | Frame], Locator]] = []

        def add_text_matchers(text: str) -> None:
            escaped = re.escape(text)
            for selector in href_matchers:
                builders.append(lambda scope, selector=selector, escaped=escaped: scope.locator(selector).filter(has_text=re.compile(escaped, re.I)))
            builders.append(lambda scope, escaped=escaped: scope.get_by_role("link").filter(has_text=re.compile(escaped, re.I)))

        for candidate in [search_value, raw_query, company_name]:
            if candidate:
                add_text_matchers(candidate)

        for selector in href_matchers:
            builders.append(lambda scope, selector=selector: scope.locator(selector))
        builders.append(lambda scope: scope.get_by_role("link"))
        return builders

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
        if self._is_account_selection_page(page):
            return True

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

    def _rbe_download_locator_builders(self, page: Page | None = None) -> list[Locator]:
        target = page
        if target is None:
            return []
        return [
            target.get_by_role("button", name=re.compile(r"copie int[ée]grale.*assujettis", re.I)),
            target.get_by_role("link", name=re.compile(r"copie int[ée]grale.*assujettis", re.I)),
            target.get_by_text(re.compile(r"copie int[ée]grale.*assujettis", re.I)),
            target.get_by_role("button", name=re.compile(r"extrait.*b[ée]n[ée]ficiaires? effectifs?", re.I)),
            target.get_by_role("link", name=re.compile(r"extrait.*b[ée]n[ée]ficiaires? effectifs?", re.I)),
            target.get_by_role("button", name=re.compile(r"b[ée]n[ée]ficiaires? effectifs?", re.I)),
            target.get_by_role("link", name=re.compile(r"b[ée]n[ée]ficiaires? effectifs?", re.I)),
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

    def _is_cloudflare_block(self, page: Page) -> bool:
        try:
            title = page.title()
        except Exception:
            title = ""

        try:
            body_text = page.locator("body").inner_text(timeout=1_000)
        except Exception:
            body_text = ""

        return bool(
            re.search(r"Attention Required|Cloudflare", title, re.I)
            or re.search(r"(sorry, you have been blocked|unable to access|cloudflare ray id|performance & security by cloudflare)", body_text, re.I)
        )

    def _try_manual_login(self, page: Page, reason: str) -> bool:
        if not self.allow_manual_login:
            return False

        print("Infogreffe: connexion automatique indisponible.")
        print(f"Raison: {reason}")
        print("La fenetre navigateur reste ouverte. Connectez-vous manuellement sur Infogreffe, puis revenez ici et appuyez sur Entree.")
        try:
            input()
        except EOFError:
            return False

        try:
            page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            pass

        if self._is_cloudflare_block(page):
            return False

        self._handle_post_login_pages(page)
        return self._is_logged_in(page)

    def _handle_post_login_pages(self, page: Page) -> None:
        deadline = time.monotonic() + ((self.timeout_ms * 2) / 1000)
        while time.monotonic() < deadline:
            if not self._is_account_selection_page(page):
                return

            if self._attempt_account_selection(page):
                try:
                    page.wait_for_load_state("networkidle", timeout=self.timeout_ms)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(500)
                continue

            if not self.allow_manual_login:
                raise AuthenticationError("La page selection-compte-client requiert une selection manuelle de compte.")

            print("Infogreffe: selection du compte client requise.")
            print("Choisissez le compte dans la fenetre navigateur, puis revenez ici et appuyez sur Entree.")
            try:
                input()
            except EOFError as exc:
                raise AuthenticationError("La page selection-compte-client requiert une selection manuelle de compte.") from exc
            page.wait_for_timeout(500)

        raise AuthenticationError("La page selection-compte-client n'a pas pu etre resolue automatiquement.")

    def _is_account_selection_page(self, page: Page) -> bool:
        if re.search(r"selection-compte-client", page.url, re.I):
            return True

        markers = [
            lambda scope: scope.get_by_text(re.compile(r"(selection du compte|selectionner un compte|compte client)", re.I)),
            lambda scope: scope.get_by_role("heading", name=re.compile(r"(selection du compte|compte client)", re.I)),
            lambda scope: scope.get_by_role("button", name=re.compile(r"(continuer|selectionner|choisir)", re.I)),
        ]
        return self._find_visible_locator_in_scopes(page, markers) is not None and re.search(r"compte", page.url + " " + self._page_text(page), re.I) is not None

    def _attempt_account_selection(self, page: Page) -> bool:
        active_patterns = [
            re.compile(r"abonnement actif", re.I),
            re.compile(r"compte actif", re.I),
            re.compile(r"actif", re.I),
            re.compile(r"active", re.I),
        ]

        if self._click_active_account_card(page):
            self._confirm_account_selection(page)
            return True

        if self._select_active_account_via_dom(page):
            self._confirm_account_selection(page)
            return True

        containers = page.locator("div, li, article, section, tr")
        try:
            container_count = min(containers.count(), 20)
        except Exception:
            container_count = 0

        for index in range(container_count):
            container = containers.nth(index)
            if not self._locator_has_any_text(container, active_patterns):
                continue

            for selector in [
                "label",
                "button",
                "a",
                "input[type='radio']",
                "input[type='checkbox']",
                "[role='radio']",
            ]:
                try:
                    candidate = container.locator(selector).first
                    candidate.wait_for(state="visible", timeout=500)
                    candidate.scroll_into_view_if_needed(timeout=self.timeout_ms)
                    candidate.click(timeout=self.timeout_ms)
                    self._confirm_account_selection(page)
                    return True
                except Exception:
                    continue

        clickable_candidates = [
            page.get_by_role("button", name=re.compile(r"(continuer|selectionner|choisir|valider|acceder)", re.I)),
            page.get_by_role("link", name=re.compile(r"(continuer|selectionner|choisir|valider|acceder)", re.I)),
            page.locator("button[type='submit']"),
            page.locator("a[href*='compte']"),
        ]

        for locator in clickable_candidates:
            try:
                candidate = locator.first
                candidate.wait_for(state="visible", timeout=750)
                candidate.scroll_into_view_if_needed(timeout=self.timeout_ms)
                candidate.click(timeout=self.timeout_ms)
                return True
            except Exception:
                continue

        selectors = [
            "input[type='radio']",
            "[role='radio']",
            ".account-card button",
            ".compte-client button",
            ".card button",
        ]
        for selector in selectors:
            try:
                candidate = page.locator(selector).first
                candidate.wait_for(state="visible", timeout=500)
                candidate.click(timeout=self.timeout_ms)
                return True
            except Exception:
                continue

        return False

    def _click_active_account_card(self, page: Page) -> bool:
        selectors = [
            "div",
            "section",
            "article",
            "li",
            "label",
        ]

        for selector in selectors:
            cards = page.locator(selector).filter(has_text=re.compile(r"Abonnement actif", re.I))
            try:
                count = min(cards.count(), 8)
            except Exception:
                count = 0

            for index in range(count):
                card = cards.nth(index)
                try:
                    card.wait_for(state="visible", timeout=500)
                    card.scroll_into_view_if_needed(timeout=self.timeout_ms)
                    card.click(timeout=self.timeout_ms, force=True)
                    return True
                except Exception:
                    pass

                try:
                    box = card.bounding_box(timeout=1_000)
                    if box and box["width"] > 150 and box["height"] > 60:
                        page.mouse.click(box["x"] + (box["width"] * 0.35), box["y"] + (box["height"] * 0.5))
                        return True
                except Exception:
                    continue

        try:
            badge = page.get_by_text(re.compile(r"Abonnement actif", re.I)).first
            badge.wait_for(state="visible", timeout=500)
            badge.scroll_into_view_if_needed(timeout=self.timeout_ms)
            box = badge.bounding_box(timeout=1_000)
            if box:
                page.mouse.click(max(box["x"] - 250, 10), box["y"] + (box["height"] * 0.5))
                return True
        except Exception:
            return False

        return False

    def _select_active_account_via_dom(self, page: Page) -> bool:
        try:
            return bool(
                page.evaluate(
                    """
                    () => {
                        const activePatterns = [
                            /abonnement actif/i,
                            /compte actif/i,
                            /offre active/i,
                            /statut actif/i,
                            /\bactif\b/i,
                            /\bactive\b/i
                        ];
                        const nodes = Array.from(document.querySelectorAll('div, li, article, section, tr, label, form'));

                        const isVisible = (element) => {
                            if (!(element instanceof HTMLElement)) return false;
                            const style = window.getComputedStyle(element);
                            const rect = element.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        };

                        const isEnabled = (element) => {
                            if (!(element instanceof HTMLElement)) return false;
                            return !element.hasAttribute('disabled') && element.getAttribute('aria-disabled') !== 'true';
                        };

                        const findClickableCard = (start) => {
                            let current = start;
                            while (current) {
                                if (!(current instanceof HTMLElement)) {
                                    current = current.parentElement;
                                    continue;
                                }

                                const style = window.getComputedStyle(current);
                                const looksClickable =
                                    current.tagName === 'A' ||
                                    current.tagName === 'BUTTON' ||
                                    current.hasAttribute('role') ||
                                    current.hasAttribute('tabindex') ||
                                    style.cursor === 'pointer' ||
                                    current.onclick !== null;

                                const rect = current.getBoundingClientRect();
                                const looksLikeCard = rect.width > 250 && rect.height > 80;

                                if (isVisible(current) && isEnabled(current) && (looksClickable || looksLikeCard)) {
                                    return current;
                                }

                                current = current.parentElement;
                            }
                            return null;
                        };

                        const fireSelection = (element) => {
                            if (!(element instanceof HTMLElement)) return false;
                            element.focus();
                            element.click();
                            element.dispatchEvent(new Event('input', { bubbles: true }));
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        };

                        const clickInside = (container) => {
                            const selectors = [
                                'input[type="radio"]',
                                'input[type="checkbox"]',
                                '[role="radio"]',
                                '[aria-checked="false"]',
                                '[data-state="unchecked"]',
                                'label',
                                'button',
                                'a'
                            ];
                            for (const selector of selectors) {
                                const candidates = Array.from(container.querySelectorAll(selector));
                                for (const candidate of candidates) {
                                    if (candidate instanceof HTMLElement && isVisible(candidate) && isEnabled(candidate)) {
                                        return fireSelection(candidate);
                                    }
                                }
                            }
                            return false;
                        };

                        const clickGlobalConfirm = () => {
                            const selectors = [
                                'button[type="submit"]',
                                'input[type="submit"]',
                                'button',
                                'a'
                            ];
                            const labels = /(continuer|valider|confirmer|selectionner|choisir|acceder|poursuivre)/i;
                            for (const selector of selectors) {
                                const candidates = Array.from(document.querySelectorAll(selector));
                                for (const candidate of candidates) {
                                    const text = candidate.textContent || candidate.getAttribute('value') || '';
                                    if (candidate instanceof HTMLElement && isVisible(candidate) && isEnabled(candidate) && labels.test(text)) {
                                        return fireSelection(candidate);
                                    }
                                }
                            }
                            return false;
                        };

                        const activeBadgeNodes = Array.from(document.querySelectorAll('*')).filter((node) => {
                            const text = node.textContent || '';
                            return node instanceof HTMLElement && isVisible(node) && /abonnement actif/i.test(text);
                        });

                        for (const badge of activeBadgeNodes) {
                            const card = findClickableCard(badge.parentElement || badge);
                            if (card && fireSelection(card)) {
                                clickGlobalConfirm();
                                return true;
                            }

                            if (clickInside(badge.parentElement || badge)) {
                                clickGlobalConfirm();
                                return true;
                            }
                        }

                        for (const node of nodes) {
                            const text = node.textContent || '';
                            if (!activePatterns.some((pattern) => pattern.test(text))) continue;
                            if (clickInside(node)) {
                                clickGlobalConfirm();
                                return true;
                            }
                        }

                        const directChoices = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"], [role="radio"], [aria-checked="false"], [data-state="unchecked"]'));
                        for (const choice of directChoices) {
                            if (!(choice instanceof HTMLElement) || !isVisible(choice) || !isEnabled(choice)) continue;
                            fireSelection(choice);
                            clickGlobalConfirm();
                            return true;
                        }

                        return false;
                    }
                    """
                )
            )
        except Exception:
            return False

    def _confirm_account_selection(self, page: Page) -> None:
        confirmation_candidates = [
            page.get_by_role("button", name=re.compile(r"(continuer|valider|confirmer|selectionner|choisir|acceder)", re.I)),
            page.get_by_role("link", name=re.compile(r"(continuer|valider|confirmer|selectionner|choisir|acceder)", re.I)),
            page.locator("button[type='submit']"),
            page.locator("input[type='submit']"),
        ]

        for locator in confirmation_candidates:
            try:
                candidate = locator.first
                candidate.wait_for(state="visible", timeout=500)
                candidate.scroll_into_view_if_needed(timeout=self.timeout_ms)
                candidate.click(timeout=self.timeout_ms)
                return
            except Exception:
                continue

        try:
            page.evaluate(
                """
                () => {
                    const labels = /(continuer|valider|confirmer|selectionner|choisir|acceder|poursuivre)/i;
                    const candidates = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
                    for (const candidate of candidates) {
                        const text = candidate.textContent || candidate.getAttribute('value') || '';
                        if (labels.test(text) && candidate instanceof HTMLElement) {
                            candidate.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        except Exception:
            pass

    def _locator_has_any_text(self, locator: Locator, patterns: list[re.Pattern[str]]) -> bool:
        try:
            text = locator.inner_text(timeout=300)
        except Exception:
            return False
        return any(pattern.search(text) for pattern in patterns)

    def _page_text(self, page: Page) -> str:
        try:
            return page.locator("body").inner_text(timeout=1_000)
        except Exception:
            return ""
