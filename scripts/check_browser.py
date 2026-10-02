"""Functional browser checks served on localhost; no official source access needed."""

import os
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(
    ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(ROOT / "web"))
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
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console", lambda message: print("Browser console:", message.type, message.text)
    )
    page.on(
        "requestfailed",
        lambda request: print("Failed request:", request.url, request.failure),
    )
    page.set_default_timeout(10000)
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    try:
        page.wait_for_function(
            "document.querySelector('#area-name').textContent!=='Cargando'",
            timeout=10000,
        )
    except Exception:
        print(
            "Page error:",
            page.locator("#error").text_content(),
            "JavaScript errors:",
            errors,
        )
        page.screenshot(path="/tmp/madrid-error.png", full_page=True)
        raise
    assert page.locator("#demo-banner").is_visible()
    assert page.locator("#map path[role=button]").count() == 9
    page.select_option("#level", "section")
    page.wait_for_function(
        "document.querySelector('#area-name').textContent.includes('Zona')"
    )
    assert page.locator("#map path[role=button]").count() == 16
    page.select_option("#preset", "born")
    page.wait_for_function("document.querySelector('#residual').textContent==='—'")
    page.select_option("#preset", "25-34")
    page.wait_for_function("document.querySelector('#residual').textContent!=='—'")
    page.fill("#age-min", "18")
    page.fill("#age-max", "29")
    page.click("#custom-age")
    page.wait_for_function(
        "document.querySelector('#distribution-caption').textContent.includes('18–29')"
    )
    page.select_option("#reliability", "all")
    page.wait_for_function(
        "document.querySelector('#coverage').textContent.includes('Incluye')"
    )
    page.wait_for_function(
        "document.querySelectorAll('#map path[role=button]').length===18"
    )
    assert page.locator('#map path[fill="url(#estimated-hatch)"]').count() == 1
    page.select_option("#window", "2014-2024")
    page.wait_for_function(
        "document.querySelector('#year-pill').textContent.includes('2014')"
    )
    page.select_option("#level", "city")
    page.wait_for_function(
        "document.querySelector('#area-name').textContent.includes('Madrid')"
    )
    page.locator("#map path[role=button]").focus()
    page.keyboard.press("Enter")
    assert page.locator("#error").is_hidden()
    assert not errors, errors
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path="/tmp/madrid-mobile.png", full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (
        "horizontal overflow on mobile"
    )
    print(
        "Browser checks passed: map, four levels, births exclusion, preset/custom ages, reliability tiers, comparison window, keyboard, mobile layout"
    )
    browser.close()

server.shutdown()
server.server_close()
