"""The in-page completion wait must read what the separate locator calls read, and return early on completion.

Opt-in (ROVO_DOM_CHECK=1): starts a throwaway headless Chrome on local HTML, never Rovo or the user's browser.
"""
import os
import time

import pytest
from playwright.sync_api import Error, sync_playwright

from cli_anything.rovo.utils.rovo_backend import wait_turn

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


def snapshot(panel, ms=0, before=99, prompt="Synthetic prompt"):
    """A wait that cannot complete early (before=99) returns the slice-end snapshot."""
    turn = wait_turn(panel, before, prompt, ms)
    turn.pop("started")
    return turn


@pytest.mark.parametrize("name", CASES)
def test_snapshot_matches_separate_reads(page, name):
    panel = panel_for(page, CASES[name])
    assert snapshot(panel) == separate_reads(panel)


def test_missing_status_reads_as_not_complete(page):
    panel = panel_for(page, GROUP.format("Synthetic prompt", ""))
    assert snapshot(panel)["status"] == ""


def test_duplicate_status_regions_fail_like_strict_locators(page):
    panel = panel_for(page, STATUS.format("Response complete.") * 2)
    with pytest.raises(Error):
        snapshot(panel)


THINKING = (STATUS.format("Rovo is thinking") + GROUP.format("Synthetic prompt", "")
            + '<button aria-label="Stop generating">x</button>')
FINISH = """() => setTimeout(() => {
  const panel = document.querySelector('[data-testid="rovo-test-panel"]');
  panel.querySelector('[data-testid="chat-history-status-live-region"]').textContent = 'Response complete.';
  panel.querySelector('button').remove();
  panel.querySelector('[data-testid="rovo-chat-message-group"]').insertAdjacentHTML('beforeend',
    '<div data-testid="assistant-response-card-layout"><div class="ak-renderer-document">Done</div></div>');
}, 300)"""


def test_wait_returns_as_soon_as_the_page_completes(page):
    panel = panel_for(page, THINKING)
    page.evaluate(FINISH)
    started_at = time.monotonic()
    turn = wait_turn(panel, 0, "Synthetic prompt", 5000)
    elapsed = time.monotonic() - started_at
    assert turn["started"] and turn["status"] == "Response complete." and turn["answer"] == "Done"
    assert 0.25 < elapsed < 1, elapsed


def test_start_seen_mid_wait_is_reported_after_it_ends(page):
    panel = panel_for(page, THINKING)
    page.evaluate("""() => setTimeout(() => {
      document.querySelector('[data-testid="chat-history-status-live-region"]').textContent = '';
      document.querySelector('button').remove();
    }, 50)""")
    turn = wait_turn(panel, 0, "Synthetic prompt", 300)
    assert turn["started"] and turn["status"] == "" and not turn["generating"]


def test_other_prompt_never_completes_early(page):
    panel = panel_for(page, THINKING)
    page.evaluate(FINISH)
    started_at = time.monotonic()
    turn = wait_turn(panel, 0, "Another prompt", 800)
    assert time.monotonic() - started_at >= 0.75 and turn["status"] == "Response complete."
