"""Click failures expose fixed labels and reasons, never Playwright page content."""
import json
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error, TimeoutError

from cli_anything.rovo.core.state import next_action, read_request, state_dir
from cli_anything.rovo.utils import rovo_backend
from test_browser_tabs import ORIGIN, PROMPT, page_fixture, run_browser


PRIVATE = 'secret@example.com /private/profile https://example.com/?token=secret private-chat-title'


@pytest.mark.parametrize("log,reason", [
    ("element is not visible", "not_visible"),
    ("element is not enabled", "not_enabled"),
    ("element is not stable", "not_stable"),
    ("element is outside of the viewport", "outside_viewport"),
    ("element was detached from the DOM, retrying", "detached"),
    (f'<div title="{PRIVATE}">private content</div> intercepts pointer events', "pointer_events_intercepted"),
    ("unrecognized reason " + PRIVATE, "unknown"),
])
def test_click_timeout_only_emits_allowlisted_reason(run_browser, log, reason, capsys):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.new_chat.click.side_effect = TimeoutError(
        f'Locator.click: Timeout 10000ms exceeded. {PRIVATE}\nCall log:\n'
        f'  - waiting for get_by_role("button", name="{PRIVATE}")\n'
        f'  - locator resolved to <button>{PRIVATE}</button>\n  - 2 × {log}\n'
    )
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and next_action(result, code) == "stop"
    assert result["click_diagnostics"] == {"control": "New chat", "reason": reason, "timed_out": True}
    assert result["message"] == f"Click timed out: New chat ({reason})."
    assert result["submission_state"] == "not_attempted"
    target.new_chat.click.assert_called_once()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    output = json.dumps(result) + capsys.readouterr().err
    for secret in PRIVATE.split():
        assert secret not in output


@pytest.mark.parametrize("name", ["Menu", "View all conversations", "Go back to Rovo chat"])
def test_chat_navigation_timeout_identifies_exact_control(run_browser, name):
    target = page_fixture(ORIGIN + "/jira/for-you")
    control = target.panel.get_by_role("button", name=name, exact=True)
    if name == "Menu":
        target.panel.get_by_role("button", name="View all conversations", exact=True).is_visible.return_value = False
    control.click.side_effect = TimeoutError('Locator.click: Timeout 10000ms exceeded.')
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result["click_diagnostics"]["control"] == name
    assert result["click_diagnostics"]["reason"] == "unknown"
    control.click.assert_called_once()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()


def test_submit_timeout_preserves_uncertain_delivery_guard(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.submit.click.side_effect = TimeoutError('Locator.click: Timeout 10000ms exceeded.\nCall log:\n  - element is not enabled')
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and next_action(result, code) == "stop"
    assert result["click_diagnostics"] == {"control": "Submit", "reason": "not_enabled", "timed_out": True}
    assert result["submission_state"] == "attempted_unknown" and result["retry_safe"] is False
    assert read_request(state_dir(tmp_path, ORIGIN, "probe"))["submission_state"] == "attempted_unknown"
    assert run_browser(prompt=PROMPT)[1] == 4
    target.submit.click.assert_called_once()


def test_capture_click_failure_keeps_completed_answer_and_safe_diagnostics(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.row.click.side_effect = TimeoutError(f'Locator.click: Timeout 10000ms exceeded.\nCall log:\n  - waiting for get_by_test_id("{PRIVATE}")')
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer"
    assert result["continuity_status"] == "unavailable" and result["retry_safe"] is False
    assert next_action(result, code) == "new_or_inspect"
    assert result["click_diagnostics"] == {"control": "Conversation row", "reason": "locator_not_resolved", "timed_out": True}
    assert PRIVATE not in json.dumps(result)
    target.submit.click.assert_called_once()


@pytest.mark.parametrize("error,reason", [
    (Error(f'Locator.click: Error: strict mode violation: {PRIVATE}'), "multiple_matches"),
    (Error(f'Locator.click: Target page, context or browser has been closed {PRIVATE}'), "target_closed"),
    (Error(PRIVATE), "unknown"),
    (Error(''), "unknown"),
    (TimeoutError('Timeout\n  - waiting for element to be visible, enabled and stable'), "unknown"),
    (TimeoutError('Locator.click: Timeout 10ms exceeded.\nCall log:\n  - element is not visible\n  - element is not enabled'), "not_enabled"),
    (TimeoutError('Timeout\n  - element is not visible\n  - click action done'), "unknown"),
    (TimeoutError('Timeout\n  - element is not visible\n  - click action done\n  - waiting for scheduled navigations to finish'), "navigation_pending"),
])
def test_other_click_failures_and_last_reported_reason(error, reason):
    control = MagicMock()
    control.click.side_effect = error
    with pytest.raises(rovo_backend.ClickError) as caught:
        rovo_backend.click_control(control, "Ask Rovo", timeout=10)
    assert caught.value.diagnostics == {"control": "Ask Rovo", "reason": reason, "timed_out": isinstance(error, TimeoutError)}
    assert PRIVATE not in str(caught.value)
    control.click.assert_called_once_with(timeout=10)


@pytest.mark.parametrize("name", ["Show more", "Ask Rovo"])
def test_preparation_click_failure_keeps_control_diagnostics(run_browser, name):
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False, authenticated=name != "Show more")
    control = target.page.get_by_role("button", name=name, exact=True)
    control.is_visible.return_value = True
    control.click.side_effect = TimeoutError('Timeout\n  - element is not stable')
    result, code = run_browser(target)
    assert code == 1 and result["click_diagnostics"]["control"] == name
    assert result["click_diagnostics"]["reason"] == "not_stable"
    assert result["submission_state"] == "not_attempted"
    control.click.assert_called_once()


def test_click_diagnostics_do_not_persist_into_later_results(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.new_chat.click.side_effect = TimeoutError('Timeout')
    assert "click_diagnostics" in run_browser(target, prompt=PROMPT)[0]
    assert "click_diagnostics" not in run_browser()[0]
