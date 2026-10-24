"""The single completion snapshot must read what the separate locator calls read.

Opt-in (ROVO_DOM_CHECK=1): starts a throwaway headless Chrome on local HTML, never Rovo or the user's browser.
"""
import os

import pytest
from playwright.sync_api import Error, sync_playwright

from cli_anything.rovo.utils.rovo_backend import observe_turn

STATUS = '<div data-testid="chat-history-status-live-region">{}</div>'
GROUP = '<div data-testid="rovo-chat-message-group"><div class="ak-renderer-document">{}</div>{}</div>'
CARD = '<div data-testid="assistant-response-card-layout">{}</div>'
DOC = '<div class="ak-renderer-document">{}</div>'

CASES = {
    "thinking": STATUS.format("Rovo is thinking")
    + GROUP.format("Synthetic prompt", "")
    + '<button aria-label="Stop generating"><svg></svg></button>',
    "complete": STATUS.format("Response complete.")
    + GROUP.format("First prompt", CARD.format(DOC.format("First answer")))
    + GROUP.format("Synthetic prompt", CARD.format(DOC.format("Line one") + DOC.format("Line two")))
    + '<button aria-label="Stop generating" style="display:none">x</button>',
    "text-labelled stop": STATUS.format("")
    + GROUP.format("Synthetic prompt", CARD.format(DOC.format("Partial")))
    + "<button><span>Stop generating</span></button>",
    "hidden stop": STATUS.format("Response complete.")
    + GROUP.format("Synthetic prompt", CARD.format(DOC.format("Done")))
    + '<button aria-label="Stop generating" style="visibility:hidden">x</button>',
    "empty welcome": STATUS.format(""),
}


@pytest.fixture(scope="module")
def page():
    if os.environ.get("ROVO_DOM_CHECK") != "1":
        pytest.skip("DOM equivalence check is opt-in: set ROVO_DOM_CHECK=1")
    with sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(channel="chrome", headless=True)
        except Error:
            pytest.skip("Google Chrome is not installed for the DOM equivalence check")
        page = browser.new_page()
        page.set_default_timeout(500)
        yield page
        browser.close()


def panel_for(page, body):
    page.set_content(f'<div data-testid="rovo-test-panel">{body}</div>')
    return page.get_by_test_id("rovo-test-panel")


def separate_reads(panel):
    """The wait loop's former per-field locator calls, kept here as the reference."""
    responses = panel.get_by_test_id("assistant-response-card-layout")
    count = responses.count()
    groups = panel.get_by_test_id("rovo-chat-message-group")
    return {
        "status": panel.get_by_test_id("chat-history-status-live-region").inner_text(),
        "generating": panel.get_by_role("button", name="Stop generating", exact=True).is_visible(),
        "count": count,
        "answer": "\n".join(responses.last.locator(".ak-renderer-document").all_inner_texts()) if count else "",
        "group_count": groups.count(),
        "user_text": groups.last.locator(".ak-renderer-document").first.inner_text() if groups.count() else "",
    }


@pytest.mark.parametrize("name", CASES)
def test_snapshot_matches_separate_reads(page, name):
    panel = panel_for(page, CASES[name])
    assert observe_turn(panel) == separate_reads(panel)


def test_missing_status_reads_as_not_complete(page):
    panel = panel_for(page, GROUP.format("Synthetic prompt", ""))
    assert observe_turn(panel)["status"] == ""


def test_duplicate_status_regions_fail_like_strict_locators(page):
    panel = panel_for(page, STATUS.format("Response complete.") * 2)
    with pytest.raises(Error):
        observe_turn(panel)
