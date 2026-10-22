"""Offline browser-boundary fixtures; no Chrome connection or Rovo requests."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Browser, Locator, Page

from cli_anything.rovo.core.state import read_request, state_dir
from cli_anything.rovo.utils import rovo_backend

ORIGIN = "https://example.atlassian.net"
ACCOUNT = "user@example.com"
PANEL = "conversation-assistant.ui.conversation-assistant"
MINI_PANEL = "conversation-assistant-mini-modal-main-container"
PROMPT = "Summarize a synthetic fixture"


def page_fixture(url, *, panel_open=True, authenticated=True, draft="",
                 before_submit_url=None, after_submit_url=None, layout=PANEL, empty_chat=False):
    page = MagicMock(spec=Page)
    page.url = url
    panel, textbox, stop, submit, new_chat, attachments, identity, more = [
        MagicMock(spec=Locator) for _ in range(8)
    ]
    panel.is_visible.return_value = panel_open
    panel.get_attribute.return_value = layout
    textbox.is_visible.return_value = True
    textbox.count.return_value = 1
    textbox.is_enabled.return_value = True
    textbox.evaluate.return_value = draft
    stop.is_visible.return_value = False
    attachments.count.return_value = 0
    identity.is_visible.return_value = authenticated
    more.is_visible.return_value = False
    submit.is_enabled.return_value = not empty_chat
    submit.is_visible.return_value = True
    new_chat.is_enabled.return_value = True
    new_chat.is_visible.return_value = True
    welcome = MagicMock(spec=Locator)
    welcome.count.return_value = int(empty_chat)
    welcome.is_visible.return_value = empty_chat

    def fill(text):
        textbox.inner_text.return_value = text
        submit.is_enabled.return_value = True
        if before_submit_url:
            page.url = before_submit_url

    textbox.fill.side_effect = fill
    responses, groups, content, user, status = [MagicMock(spec=Locator) for _ in range(5)]
    responses.count.return_value = 0
    responses.last.locator.return_value = content
    content.all_inner_texts.return_value = ["Synthetic answer"]
    groups.count.return_value = 0 if empty_chat else 1
    groups.last.locator.return_value.first = user
    user.inner_text.return_value = PROMPT
    status.inner_text.side_effect = ["Rovo is thinking", "Response complete."]

    def send():
        responses.count.return_value = 1
        groups.count.return_value = 1
        if after_submit_url:
            page.url = after_submit_url

    submit.click.side_effect = send
    panel.get_by_test_id.side_effect = {
        "assistant-response-card-layout": responses,
        "rovo-chat-message-group": groups,
        "chat-history-status-live-region": status,
    }.__getitem__
    panel.get_by_role.side_effect = lambda role, name=None, **kw: (
        textbox if role == "textbox" else welcome if role == "heading" and name.search("How can I help, Fixture?")
        else attachments if not isinstance(name, str)
        else {"Stop generating": stop, "Submit": submit, "New chat": new_chat}[name]
    )
    roots = {}
    for test_id in (PANEL, MINI_PANEL):
        root = panel if test_id == layout else MagicMock(spec=Locator)
        root.is_visible.return_value = panel_open and test_id == layout
        root.all.return_value = [panel] if test_id == layout else []
        roots[test_id] = root
    page.get_by_test_id.side_effect = roots.__getitem__
    page.get_by_role.side_effect = lambda role, name, **kw: {
        ACCOUNT: identity, "Show more": more,
    }[name]
    return SimpleNamespace(page=page, panel=panel, roots=roots, submit=submit,
                           textbox=textbox, stop=stop, attachments=attachments,
                           responses=responses, groups=groups, welcome=welcome,
                           status=status, new_chat=new_chat)


@pytest.fixture
def run_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def run(*fixtures, **kwargs):
        browser = MagicMock(spec=Browser)
        browser.contexts = [SimpleNamespace(pages=[f.page for f in fixtures])]
        runtime = MagicMock()
        runtime.__enter__.return_value.chromium.connect_over_cdp.return_value = browser
        monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: runtime)
        result = rovo_backend.operate(ORIGIN, "probe", ACCOUNT, **kwargs)
        browser.close.assert_called_once()
        assert not list(tmp_path.rglob("control.lock"))
        return result

    return run


@pytest.mark.parametrize("path", ["/jira/for-you", "/browse/DEMO-1"])
def test_status_accepts_board_and_issue_routes(run_browser, path):
    target = page_fixture(ORIGIN + path)
    result, code = run_browser(target)
    assert code == 0, result
    assert result["readiness"] == "authenticated_ui"
    assert result["active_generation"] is False and result["retry_safe"] is True
    target.submit.click.assert_not_called()


@pytest.mark.parametrize("target_path", ["/jira/for-you", "/browse/DEMO-1"])
def test_selects_only_open_panel_among_multiple_tabs(run_browser, target_path):
    closed = page_fixture(ORIGIN + "/jira/software/projects/DEMO/boards/1", panel_open=False)
    target = page_fixture(ORIGIN + target_path)
    result, code = run_browser(closed, target)
    assert code == 0, result
    assert result["readiness"] == "authenticated_ui"
    closed.page.get_by_role.assert_not_called()
    target.page.get_by_role.assert_called()


@pytest.mark.parametrize("panels, message", [
    ([], "/browse/"), ([False, False], "Open Rovo"), ([True, True], "multiple"),
])
def test_missing_or_ambiguous_panel_never_sends(run_browser, tmp_path, panels, message):
    tabs = [page_fixture(ORIGIN + f"/jira/boards/{i}", panel_open=opened)
            for i, opened in enumerate(panels)]
    result, code = run_browser(*tabs, prompt=PROMPT)
    assert code == 1 and message in result["message"], result
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    assert not list(tmp_path.rglob("request.json"))
    for tab in tabs:
        tab.submit.click.assert_not_called()
        tab.page.get_by_role.assert_not_called()


@pytest.mark.parametrize("url", [
    "https://other.atlassian.net/browse/DEMO-1",
    "https://example.atlassian.net.evil.test/jira/for-you",
    ORIGIN + "/wiki/spaces/DEMO", ORIGIN + "/browse-other/DEMO-1",
])
def test_unrelated_tabs_cannot_be_selected(run_browser, url):
    unrelated = page_fixture(url)
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    result, code = run_browser(unrelated, target)
    assert code == 0, result
    unrelated.page.get_by_test_id.assert_not_called()
    unrelated.page.get_by_role.assert_not_called()


def test_wrong_account_on_selected_issue_tab_blocks_send(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", authenticated=False)
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 2 and result["execution_status"] == "authentication_required", result
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


def test_issue_tab_draft_is_preserved(run_browser):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", draft="Unsent work")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "Existing draft" in result["message"], result
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()


@pytest.mark.parametrize("path", ["/jira/for-you", "/browse/DEMO-1"])
def test_supported_route_completes_one_guarded_send(run_browser, tmp_path, path):
    target = page_fixture(ORIGIN + path)
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer", result
    target.new_chat.click.assert_called_once()
    target.submit.click.assert_called_once()
    record = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert record["submission_state"] == "observed_submitted"
    assert record["execution_status"] == "completed"


@pytest.mark.parametrize("url", ["https://other.atlassian.net/browse/DEMO-1", ORIGIN + "/wiki/spaces/DEMO"])
def test_navigation_before_submit_never_sends(run_browser, tmp_path, url):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", before_submit_url=url)
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "Target or draft changed" in result["message"], result
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("url", ["https://other.atlassian.net/browse/DEMO-1", ORIGIN + "/wiki/spaces/DEMO"])
def test_navigation_after_submit_keeps_uncertainty_and_never_reselects(run_browser, tmp_path, url):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", after_submit_url=url)
    other = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
    result, code = run_browser(target, other, prompt=PROMPT)
    assert code == 1 and "after submission" in result["message"], result
    assert result["submission_state"] == "attempted_unknown" and result["retry_safe"] is False
    target.submit.click.assert_called_once()
    other.submit.click.assert_not_called()
    record = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert record["submission_state"] == "attempted_unknown"
    result, code = rovo_backend.operate(ORIGIN, "another-session", ACCOUNT, prompt=PROMPT)
    assert code == 4 and result["retry_safe"] is False
    target.submit.click.assert_called_once()


@pytest.mark.parametrize("action", ["ask", "chat_list", "chat_export"])
def test_mini_modal_is_detected_but_unverified_operations_do_not_mutate(run_browser, tmp_path, action):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL)
    target.new_chat.is_enabled.return_value = False
    kwargs = {"prompt": PROMPT} if action == "ask" else {"action": action}
    if action == "chat_export":
        kwargs["chat_id"] = "12345678-1234-4234-8234-123456789abc"
    result, code = run_browser(target, **kwargs)
    assert code == 1 and result.get("error_code") == "rovo_layout_unverified", result
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    assert "readiness" not in result and "active_generation" not in result
    target.new_chat.click.assert_not_called()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("state", ["draft", "attachment", "generating", "response"])
def test_mini_modal_nonempty_states_never_enable_sending(run_browser, tmp_path, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL,
                          draft="Unsent work" if state == "draft" else "")
    target.attachments.count.return_value = int(state == "attachment")
    target.stop.is_visible.return_value = state == "generating"
    target.responses.count.return_value = int(state == "response")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result.get("error_code") == "rovo_layout_unverified", result
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("layout", [PANEL, MINI_PANEL])
def test_hidden_panel_duplicates_do_not_hide_the_only_visible_panel(run_browser, layout):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=layout)
    hidden = MagicMock(spec=Locator)
    hidden.is_visible.return_value = False
    target.roots[layout].all.return_value = [hidden, target.panel]
    result, code = run_browser(target)
    if layout == PANEL:
        assert code == 0 and result["readiness"] == "authenticated_ui", result
    else:
        assert code == 0 and result["readiness"] == "authenticated_ui_read_only", result
        assert result["active_generation"] is None


@pytest.mark.parametrize("kind", ["duplicate", "mixed", "nested"])
def test_multiple_visible_roots_in_one_tab_are_rejected(run_browser, tmp_path, kind):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    other = MagicMock(spec=Locator)
    other.is_visible.return_value = True
    if kind == "duplicate":
        target.roots[PANEL].all.return_value = [target.panel, other]
    else:
        target.roots[MINI_PANEL].all.return_value = [other]
        # Containment must not silently choose the outer or inner root.
        if kind == "nested":
            lookup = target.panel.get_by_test_id.side_effect
            target.panel.get_by_test_id.side_effect = lambda test_id: (
                other if test_id == MINI_PANEL else lookup(test_id)
            )
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "multiple" in result["message"].lower(), result
    target.page.get_by_role.assert_not_called()
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("state", ["missing", "hidden", "duplicate", "disabled"])
def test_unusable_legacy_composer_blocks_before_new_chat(run_browser, tmp_path, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.textbox.count.return_value = {"missing": 0, "duplicate": 2}.get(state, 1)
    target.textbox.is_visible.return_value = state != "hidden"
    target.textbox.is_enabled.return_value = state != "disabled"
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "composer" in result["message"].lower(), result
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("state", ["attachment", "generating"])
def test_legacy_nonempty_guards_preserve_chat(run_browser, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.attachments.count.return_value = int(state == "attachment")
    target.stop.is_visible.return_value = state == "generating"
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "Existing draft" in result["message"], result
    target.new_chat.click.assert_not_called()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()


def test_disabled_new_chat_is_not_assumed_empty(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.new_chat.is_enabled.return_value = False
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "New chat" in result["message"], result
    target.new_chat.click.assert_not_called()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("path", ["/jira/for-you", "/browse/DEMO-1"])
def test_verified_empty_sidebar_sends_without_clicking_disabled_new_chat(run_browser, tmp_path, path):
    target = page_fixture(ORIGIN + path, empty_chat=True)
    target.new_chat.is_enabled.return_value = False
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer", result
    target.new_chat.click.assert_not_called()
    target.page.wait_for_function.assert_not_called()
    target.textbox.fill.assert_called_once_with(PROMPT)
    target.submit.click.assert_called_once()
    record = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert record["submission_state"] == "observed_submitted"
    assert record["execution_status"] == "completed"


@pytest.mark.parametrize("state", [
    "draft", "attachment", "generating", "turn", "response", "missing_welcome",
    "hidden_welcome", "duplicate_welcome", "hidden_new_chat", "hidden_submit",
    "enabled_submit", "mini_modal",
])
def test_disabled_new_chat_rejects_unverified_empty_states(run_browser, tmp_path, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", empty_chat=True,
                          draft="Unsent work" if state == "draft" else "",
                          layout=MINI_PANEL if state == "mini_modal" else PANEL)
    target.new_chat.is_enabled.return_value = False
    target.new_chat.is_visible.return_value = state != "hidden_new_chat"
    target.submit.is_enabled.return_value = state == "enabled_submit"
    target.submit.is_visible.return_value = state != "hidden_submit"
    target.attachments.count.return_value = int(state == "attachment")
    target.stop.is_visible.return_value = state == "generating"
    target.groups.count.return_value = int(state == "turn")
    target.responses.count.return_value = int(state == "response")
    target.welcome.count.return_value = {"missing_welcome": 0, "duplicate_welcome": 2}.get(state, 1)
    target.welcome.is_visible.return_value = state != "hidden_welcome"
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1, result
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    if state == "mini_modal":
        assert result["error_code"] == "rovo_layout_unverified"
    target.new_chat.click.assert_not_called()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


def test_legacy_and_mini_modal_in_different_tabs_are_ambiguous(run_browser):
    legacy = page_fixture(ORIGIN + "/jira/for-you")
    mini = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL)
    result, code = run_browser(legacy, mini, prompt=PROMPT)
    assert code == 1 and "multiple tabs" in result["message"], result
    for target in (legacy, mini):
        target.page.get_by_role.assert_not_called()
        target.submit.click.assert_not_called()


@pytest.mark.parametrize("prompt", [None, PROMPT])
def test_mini_modal_wrong_account_is_not_authenticated(run_browser, prompt):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL, authenticated=False)
    result, code = run_browser(target, prompt=prompt)
    assert code == 2 and result["execution_status"] == "authentication_required", result
    target.submit.click.assert_not_called()


def test_panel_disappearing_after_account_check_does_not_reselect(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.roots[PANEL].all.side_effect = [[target.panel], []]
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "Open Rovo" in result["message"], result
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("state", ["empty", "completed", "draft", "generating"])
def test_mini_modal_status_confirms_account_without_claiming_send_readiness(run_browser, tmp_path, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL,
                          draft="Unsent work" if state == "draft" else "")
    target.responses.count.return_value = 4 if state == "completed" else 0
    target.status.inner_text.side_effect = None
    target.status.inner_text.return_value = "Message sent."
    target.new_chat.is_enabled.return_value = state == "completed"
    target.submit.is_enabled.return_value = False
    target.stop.is_visible.return_value = state == "generating"
    target.textbox.is_enabled.return_value = state != "generating"
    result, code = run_browser(target)
    assert code == 0 and result["execution_status"] == "completed", result
    assert result["readiness"] == "authenticated_ui_read_only"
    assert result["active_generation"] is None and result["retry_safe"] is True
    assert "unverified" in result["message"]
    assert "answer" not in result and "error_code" not in result
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize("state", ["missing", "hidden", "duplicate"])
def test_mini_modal_status_requires_one_visible_composer(run_browser, tmp_path, state):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL)
    target.textbox.count.return_value = {"missing": 0, "duplicate": 2}.get(state, 1)
    target.textbox.is_visible.return_value = state != "hidden"
    result, code = run_browser(target)
    assert code == 1 and "composer" in result["message"].lower(), result
    assert "readiness" not in result
    target.textbox.fill.assert_not_called()
    target.new_chat.click.assert_not_called()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))
