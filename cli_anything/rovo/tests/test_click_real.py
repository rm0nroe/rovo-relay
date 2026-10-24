"""A click the page never acknowledges is labelled input_not_acknowledged, not unknown.

Opt-in (ROVO_DOM_CHECK=1): starts a throwaway headless Chrome on local HTML, never Rovo or the user's browser.
"""
import os

import pytest
from playwright.sync_api import Error, sync_playwright

from cli_anything.rovo.utils.rovo_backend import ClickError, click_control


@pytest.fixture(scope="module")
def page():
    if os.environ.get("ROVO_DOM_CHECK") != "1":
        pytest.skip("Real-browser click check is opt-in: set ROVO_DOM_CHECK=1")
    with sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(channel="chrome", headless=True)
        except Error:
            pytest.skip("Google Chrome is not installed for the real-browser click check")
        yield browser.new_page()
        browser.close()


def test_busy_page_click_is_input_not_acknowledged(page):
    # Jira's main thread stays busy after the input is sent, as during a sign-in bounce.
    page.set_content('<button aria-label="Show more" onmousedown="const t = Date.now(); while (Date.now() - t < 2500) {}">Show more</button>')
    with pytest.raises(ClickError) as caught:
        click_control(page.get_by_role("button", name="Show more", exact=True), "Show more", timeout=1000)
    assert caught.value.diagnostics == {"control": "Show more", "reason": "input_not_acknowledged", "timed_out": True}
    page.wait_for_timeout(2000)
