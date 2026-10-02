"""Exercise the observed research site, including partitioned data and city windows."""

import functools
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "data/derived/research-site"
REPORT = json.loads((ROOT / "docs/audit/research-results.json").read_text())


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(
    ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SITE))
)
Thread(target=server.serve_forever, daemon=True).start()
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=None
        if os.getenv("MADRID_BROWSER") == "playwright"
        else "/usr/bin/chromium",
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.set_default_timeout(30000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    failures = []
    page.on(
        "response",
        lambda response: (
            failures.append(response.url) if response.status >= 400 else None
        ),
    )
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    page.wait_for_function(
        "document.querySelector('#area-name').textContent !== 'Cargando'"
    )
    assert (
        page.locator("#demo-banner b").text_content() == "Resultados de investigación"
    )
    assert "históricos aprobados" in page.locator("#coverage").text_content()
    assert (
        page.locator("#map path[role=button]").count()
        == REPORT["spatial"]["area_counts"]["district"]
    )
    page.select_option("#level", "barrio")
    page.wait_for_function(
        f"document.querySelectorAll('#map path[role=button]').length === {REPORT['spatial']['area_counts']['barrio']}"
    )
    page.select_option("#level", "section")
    page.wait_for_function(
        f"document.querySelectorAll('#map path[role=button]').length === {REPORT['spatial']['area_counts']['section']}"
    )
    page.select_option("#preset", "born")
    page.wait_for_function("document.querySelector('#residual').textContent==='—'")
    page.select_option("#preset", "25-34")
    page.wait_for_function("document.querySelector('#residual').textContent!=='—'")
    for window in ("2015-2025-city", "2014-2024-city"):
        page.select_option("#window", window)
        page.wait_for_function(
            "document.querySelector('#area-name').textContent==='Madrid · toda la ciudad'"
        )
        page.wait_for_function(
            f"document.querySelector('#year-pill').textContent === '{window[:4]} → {window[5:9]}'"
        )
        page.wait_for_function(
            "document.querySelectorAll('#map path[role=button]').length===1"
        )
        assert page.locator("#level").input_value() == "city"
        assert (
            "Madrid_closed_band_approximation_under95"
            in page.locator("#sensitivity").text_content()
        )
        page.fill("#age-min", "18")
        page.fill("#age-max", "29")
        page.click("#custom-age")
        page.wait_for_function(
            "document.querySelector('#distribution-caption').textContent.includes('18–29')"
        )
        page.select_option("#preset", "born")
        page.wait_for_function("document.querySelector('#residual').textContent==='—'")
    page.select_option("#window", "2015-2025-areas")
    page.select_option("#level", "district")
    page.wait_for_function(
        f"document.querySelectorAll('#map path[role=button]').length === {REPORT['spatial']['area_counts']['district']}"
    )
    page.locator("#map path[role=button]").first.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('#actual').textContent!=='—'")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(
        path=str(ROOT / "reports/research-explorer-mobile.png"), full_page=True
    )
    page.set_viewport_size({"width": 1280, "height": 900})
    page.screenshot(path=str(ROOT / "reports/research-explorer.png"), full_page=True)
    assert not errors, errors
    assert not failures, failures
    browser.close()
server.shutdown()
print(
    "Research browser passed: real maps, three windows, lazy indicators, cohort exclusions, custom ages, keyboard, mobile, no failed requests"
)
