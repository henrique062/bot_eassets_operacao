#!/usr/bin/env python3
"""
eAssets AI JSON scraper.

Credentials are read from environment variables by the Flask app. Do not hardcode
secrets in this file.
"""

import json
import os
import re
import time
from datetime import datetime, timezone


class EassetsScrapeError(RuntimeError):
    pass


def _first_ready(page, locators, *, timeout=5_000, enabled=False):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    last_error = None
    for locator in locators:
        try:
            item = locator.first
            item.wait_for(state="visible", timeout=timeout)
            if enabled:
                page.wait_for_function(
                    "(el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true'",
                    arg=item.element_handle(timeout=timeout),
                    timeout=timeout,
                )
            return item
        except Exception as exc:
            if not isinstance(exc, PlaywrightTimeoutError):
                last_error = exc
            continue
    if last_error:
        raise last_error
    return None


def _fill_first(page, locators, value, field_name):
    item = _first_ready(page, locators, timeout=4_000)
    if not item:
        raise EassetsScrapeError(f"Campo de {field_name} nao encontrado na tela de login.")
    item.fill(value)


def _click_first(page, locators, label, *, timeout=8_000):
    item = _first_ready(page, locators, timeout=timeout, enabled=True)
    if not item:
        raise EassetsScrapeError(f"Botao/acao nao encontrado: {label}.")
    item.click()
    return item


def _looks_logged_in(page):
    checks = [
        page.get_by_title("Export for AI"),
        page.get_by_role("button", name=re.compile("export.*ai|ai", re.I)),
        page.get_by_text(re.compile("overview", re.I)),
        page.get_by_text(re.compile("LLM Integration", re.I)),
    ]
    return _first_ready(page, checks, timeout=2_000) is not None


def _login_if_needed(page, email, password):
    if _looks_logged_in(page):
        return

    email_locators = [
        page.locator('input[type="email"]'),
        page.locator('input[name="email"]'),
        page.locator('input[name="username"]'),
        page.get_by_label(re.compile("e-?mail|usuario|user", re.I)),
        page.get_by_placeholder(re.compile("e-?mail|usuario|user", re.I)),
    ]
    password_locators = [
        page.locator('input[type="password"]'),
        page.locator('input[name="password"]'),
        page.get_by_label(re.compile("senha|password", re.I)),
        page.get_by_placeholder(re.compile("senha|password", re.I)),
    ]

    _fill_first(page, email_locators, email, "email")
    _fill_first(page, password_locators, password, "senha")

    _click_first(
        page,
        [
            page.get_by_role("button", name=re.compile("entrar|login|log in|sign in|acessar", re.I)),
            page.locator('button[type="submit"]'),
            page.locator('input[type="submit"]'),
        ],
        "login",
        timeout=6_000,
    )
    page.wait_for_load_state("networkidle", timeout=45_000)
    page.wait_for_timeout(1_000)

    if not _looks_logged_in(page):
        raise EassetsScrapeError("Login enviado, mas o painel/exportacao IA nao apareceu.")


def _select_full_mode(page):
    full_button = _first_ready(
        page,
        [
            page.get_by_role("button", name=re.compile("^full$", re.I)),
            page.get_by_text(re.compile("^full$", re.I)),
        ],
        timeout=2_000,
    )
    if full_button:
        try:
            full_button.click()
        except Exception:
            pass


def _open_ai_export_panel(page):
    _click_first(
        page,
        [
            page.get_by_title("Export for AI"),
            page.locator('button[title*="Export for AI"]'),
            page.get_by_role("button", name=re.compile("export.*ai|ai", re.I)),
        ],
        "Export for AI",
        timeout=30_000,
    )
    page.wait_for_timeout(800)
    _select_full_mode(page)


def _capture_clipboard_writes(page):
    page.evaluate(
        """
        () => {
            window.__eassetsCopiedTexts = [];
            const writeText = async (text) => {
                window.__eassetsCopiedTexts.push(String(text || ""));
                return undefined;
            };

            try {
                if (navigator.clipboard) {
                    Object.defineProperty(navigator.clipboard, "writeText", {
                        configurable: true,
                        value: writeText,
                    });
                }
            } catch (e) {}

            try {
                Object.defineProperty(navigator, "clipboard", {
                    configurable: true,
                    value: { writeText },
                });
            } catch (e) {}
        }
        """
    )


def _clipboard_texts(page):
    return page.evaluate("() => window.__eassetsCopiedTexts || []")


def _export_progress(page):
    try:
        return page.evaluate(
            """
            () => {
                const asides = [...document.querySelectorAll("aside")];
                const text = (asides.at(-1)?.innerText || document.body.innerText || "");
                const match = text.match(/\\d+\\/\\d+ \\(\\d+%\\) [A-Z0-9]+/);
                return match ? match[0] : null;
            }
            """
        )
    except Exception:
        return None


def _json_from_text(raw):
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as exc:
        raise EassetsScrapeError(f"Exportacao nao retornou JSON valido: {exc}") from exc


def _export_json(page, timeout_ms):
    copy_button = _first_ready(
        page,
        [
            page.get_by_title("Copy to clipboard"),
            page.locator('button[title*="Copy"]'),
            page.get_by_role("button", name=re.compile("^copy$", re.I)),
        ],
        timeout=timeout_ms,
        enabled=True,
    )
    if not copy_button:
        raise EassetsScrapeError("Botao de copia/exportacao do JSON nao ficou disponivel.")

    _capture_clipboard_writes(page)

    click_started_at = time.monotonic()
    try:
        copy_button.click(timeout=min(10_000, timeout_ms))
    except Exception:
        copy_button.evaluate("el => el.click()")

    js_click_attempted = False
    last_progress = None
    last_invalid = None
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        for raw in reversed(_clipboard_texts(page)):
            if not raw:
                continue
            try:
                return _json_from_text(raw)
            except EassetsScrapeError as exc:
                last_invalid = exc

        last_progress = _export_progress(page) or last_progress

        if not js_click_attempted and time.monotonic() - click_started_at > 3:
            copy_button.evaluate("el => el.click()")
            js_click_attempted = True

        page.wait_for_timeout(1_000)

    if last_invalid:
        raise last_invalid
    detail = f" Ultimo progresso: {last_progress}." if last_progress else ""
    raise EassetsScrapeError(f"Timeout aguardando exportacao JSON pelo painel eAssets.{detail}")


def validate_eassets_payload(data):
    if not isinstance(data, dict):
        raise EassetsScrapeError("Payload baixado nao e um objeto JSON.")
    coins = data.get("data")
    if not isinstance(coins, dict) or not coins:
        raise EassetsScrapeError("JSON baixado nao contem data com moedas.")

    symbols = data.get("symbols")
    if isinstance(symbols, int) and symbols > 0 and len(coins) < symbols:
        raise EassetsScrapeError(
            f"Snapshot incompleto: JSON trouxe {len(coins)} moedas, mas informa {symbols} simbolos."
        )

    if not data.get("timestamp"):
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
    if not data.get("exchange"):
        data["exchange"] = "eassets"
    return data


def scrape_eassets_json(
    *,
    email=None,
    password=None,
    url="https://eassets.ai/panel",
    headless=True,
    timeout_ms=120_000,
):
    email = email or os.getenv("EASSETS_EMAIL")
    password = password or os.getenv("EASSETS_PASSWORD")
    if not email or not password:
        raise EassetsScrapeError(
            "Credenciais ausentes. Configure EASSETS_EMAIL e EASSETS_PASSWORD no ambiente."
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise EassetsScrapeError(
            "Playwright nao esta instalado. Rode: pip install -r requirements.txt e python -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            _login_if_needed(page, email, password)
            _open_ai_export_panel(page)
            data, raw = _export_json(page, timeout_ms)
            data = validate_eassets_payload(data)
            return data, raw
        finally:
            context.close()
            browser.close()
