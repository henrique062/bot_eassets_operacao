#!/usr/bin/env python3
"""
eAssets AI JSON scraper.

Credentials are read from environment variables by the Flask app. Do not hardcode
secrets in this file.

Extra function added at the bottom: ingest_snapshot() — persists scraped data
into PostgreSQL (eassets_snapshots, eassets_metrics, eassets_raw_snapshots) and
notifies the Rust core via rust_bridge.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# Allow importing gerar_painel from the project root (one level up from python_api)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


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
    stall_timeout_s = max(timeout_ms / 1000, 30)
    hard_timeout_s = max(stall_timeout_s * 3, 300)
    deadline = time.monotonic() + hard_timeout_s
    last_progress_change = time.monotonic()

    while time.monotonic() < deadline:
        for raw in reversed(_clipboard_texts(page)):
            if not raw:
                continue
            try:
                return _json_from_text(raw)
            except EassetsScrapeError as exc:
                last_invalid = exc

        current_progress = _export_progress(page)
        if current_progress and current_progress != last_progress:
            last_progress = current_progress
            last_progress_change = time.monotonic()

        if not js_click_attempted and time.monotonic() - click_started_at > 3:
            copy_button.evaluate("el => el.click()")
            js_click_attempted = True

        if time.monotonic() - last_progress_change > stall_timeout_s:
            break

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


# ---------------------------------------------------------------------------
# Persistence layer (added to original scraper logic)
# ---------------------------------------------------------------------------

async def ingest_snapshot(
    data: dict,
    raw_json: str,
    pool,
    rust_bridge_url: str,
) -> int:
    """Persist a scraped eAssets snapshot to PostgreSQL and notify the Rust engine.

    Steps:
    1. Compute per-symbol scores via gerar_painel.build_rows().
    2. INSERT into eassets_snapshots.
    3. Batch INSERT into eassets_metrics (one row per symbol).
    4. INSERT into eassets_raw_snapshots.
    5. POST {rust_bridge_url}/internal/snapshot-updated?snap_id={id}.

    Args:
        data:            Validated dict returned by scrape_eassets_json().
        raw_json:        Original raw JSON string.
        pool:            asyncpg.Pool instance.
        rust_bridge_url: Base URL of the Rust core service.

    Returns:
        The id of the newly inserted eassets_snapshots row.
    """
    import httpx
    from loguru import logger

    from db import repositories as repo

    # 1. Compute scores
    try:
        import gerar_painel  # noqa: PLC0415
        coin_data = data.get("data", data)
        rows = gerar_painel.build_rows(coin_data)
    except Exception as exc:
        logger.warning("gerar_painel.build_rows failed, ingesting without metrics: {}", exc)
        rows = []

    # Determine BTC reset state
    btc = data.get("data", data).get("BTCUSDT") if isinstance(data.get("data"), dict) else None
    btc_reset: bool | None = None
    if btc:
        try:
            macro = gerar_painel.btc_macro(btc)
            btc_reset = macro.get("reset", False)
        except Exception:
            pass

    # 2. INSERT snapshot header
    snap_meta = {
        "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "exchange": data.get("exchange"),
        "setup": data.get("setup"),
        "mode": data.get("mode"),
        "symbols": data.get("symbols"),
        "source": "scraper",
        "btc_reset": btc_reset,
        "trigger": "auto",
    }
    snap_id = await repo.insert_snapshot(pool, snap_meta)
    logger.info("Snapshot inserted snap_id={}", snap_id)

    # 3. INSERT metrics rows
    if rows:
        # Enrich rows with raw numeric values needed by the schema
        coin_data_raw = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        metric_rows = []
        for rank, r in enumerate(rows, 1):
            sym = r["symbol"]
            raw_e = coin_data_raw.get(sym, {})
            metric_rows.append({
                **r,
                "rank": rank,
                "price_raw": raw_e.get("price"),
                "oi_usd_raw": raw_e.get("oi:5m"),
                "raw_json": json.dumps(raw_e),
            })
        try:
            await repo.insert_metrics(pool, snap_id, metric_rows)
            logger.info("Metrics inserted: {} symbols", len(metric_rows))
        except Exception as exc:
            logger.error("Failed to insert metrics: {}", exc)

    # 4. INSERT raw snapshot
    await repo.insert_raw_snapshot(pool, snap_id, raw_json, status="ok")

    # 5. Notify Rust core
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            await client.post(
                f"{rust_bridge_url}/internal/snapshot-updated",
                params={"snap_id": snap_id},
            )
    except Exception as exc:
        logger.warning("Failed to notify Rust core of snapshot {}: {}", snap_id, exc)

    return snap_id
