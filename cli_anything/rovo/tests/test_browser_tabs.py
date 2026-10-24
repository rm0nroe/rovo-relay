"""Offline browser-boundary fixtures; no Chrome connection or Rovo requests."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from itertools import count

import pytest
from contextlib import contextmanager
from playwright.sync_api import Browser, Error, Locator, Page, TimeoutError

from cli_anything.rovo.core.state import load_images, read_request, state_dir
from cli_anything.rovo.utils import rovo_backend

ORIGIN = "https://example.atlassian.net"
ACCOUNT = "user@example.com"
PANEL = "conversation-assistant.ui.conversation-assistant"
MINI_PANEL = "conversation-assistant-mini-modal-main-container"
PROMPT = "Summarize a synthetic fixture"
MESSAGE_ID = "00000000-0000-4000-8000-{:012d}"


def page_fixture(url, *, panel_open=True, authenticated=True, draft="",
                 before_submit_url=None, after_submit_url=None, layout=PANEL, empty_chat=False):
    page = MagicMock(spec=Page)
    page.url = url
    page.is_closed.return_value = False
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
    # Synthetic server message ID on the last group; each submission creates a new one.
    message = MagicMock(spec=Locator)
    message.count.return_value = 1
    message.get_attribute.return_value = MESSAGE_ID.format(0)
    renderer = groups.last.locator.return_value
    groups.last.locator.side_effect = lambda selector: message if selector == "[data-message-id]" else renderer
    user.inner_text.return_value = PROMPT
    status.inner_text.side_effect = ["Rovo is thinking", "Response complete."]

    # Rovo's send request names the conversation in its URL; tests may replace these.
    listeners = {}
    page.on.side_effect = lambda event, handler: listeners.setdefault(event, []).append(handler)
    page.remove_listener.side_effect = lambda event, handler: listeners[event].remove(handler)
    sends = ["12345678-1234-4234-8234-123456789abc"]

    def send():
        responses.count.return_value += 1
        groups.count.return_value += 1
        message.get_attribute.return_value = MESSAGE_ID.format(submit.click.call_count)
        for chat in sends:
            request = SimpleNamespace(method="POST", url=f"{ORIGIN}/gateway/api/assist/rovo/v1/chat/conversation/{chat}/message/stream/sse")
            for handler in list(listeners.get("request", [])):
                handler(request)
        if after_submit_url:
            page.url = after_submit_url

    submit.click.side_effect = send
    # One in-page completion wait returns one snapshot; "started" is what the page saw during it.
    panel.evaluate.side_effect = lambda script, arg=None: {
        "status": status.inner_text(), "generating": stop.is_visible(), "count": responses.count(),
        "answer": "\n".join(content.all_inner_texts()) if responses.count() else "",
        "group_count": groups.count(), "user_text": user.inner_text() if groups.count() else "",
        "started": False,
    }
    groups.last.get_by_test_id.return_value.locator.return_value = content
    new_chat.click.side_effect = lambda: (setattr(responses.count, "return_value", 0), setattr(groups.count, "return_value", 0))
    search, menu, all_chats, back, rows, row, history = [MagicMock(spec=Locator) for _ in range(7)]
    search.is_visible.return_value = False
    search.input_value.return_value = ""
    rows.evaluate_all.side_effect = lambda script: ["12345678-1234-4234-8234-123456789abc"] if submit.click.call_count else []
    panel.locator.return_value = rows
    panel.get_by_test_id.side_effect = {
        "assistant-response-card-layout": responses,
        "rovo-chat-message-group": groups,
        "chat-history-status-live-region": status,
        "chat-history-container": history,
        "chat-conversation-list-refresh-row-12345678-1234-4234-8234-123456789abc": row,
    }.__getitem__
    panel.get_by_role.side_effect = lambda role, name=None, **kw: (
        textbox if role == "textbox" else welcome if role == "heading" and name.search("How can I help, Fixture?")
        else attachments if not isinstance(name, str)
        else named(name)
    )
    # Upload chips are named after each file; tests may preseed one to change its behavior.
    add, upload = MagicMock(spec=Locator), MagicMock(spec=Locator)
    chips = {}
    named = lambda name: chips.setdefault(name, MagicMock(spec=Locator)) if name.startswith("Remove file ") or name.endswith(" PNG") else {
        "Stop generating": stop, "Submit": submit, "New chat": new_chat, "Add": add,
        "Search conversations...": search, "Menu": menu, "View all conversations": all_chats,
        "Go back to Rovo chat": back}[name]
    roots = {}
    for test_id in (PANEL, MINI_PANEL):
        root = panel if test_id == layout else MagicMock(spec=Locator)
        root.is_visible.return_value = panel_open and test_id == layout
        root.all.return_value = [panel] if test_id == layout else []
        roots[test_id] = root
    page.get_by_test_id.side_effect = roots.__getitem__
    launcher = MagicMock(spec=Locator)
    launcher.is_visible.return_value = True
    launcher.is_enabled.return_value = True
    launcher.click.side_effect = lambda **kw: panel.is_visible.__setattr__("return_value", True)
    page.get_by_role.side_effect = lambda role, name, **kw: {
        ACCOUNT: identity, "Show more": more, "Ask Rovo": launcher, "Upload file": upload,
    }[name]
    chooser = page.expect_file_chooser.return_value.__enter__.return_value
    return SimpleNamespace(page=page, panel=panel, roots=roots, submit=submit,
                           textbox=textbox, stop=stop, attachments=attachments,
                           responses=responses, groups=groups, welcome=welcome,
                           status=status, new_chat=new_chat, launcher=launcher, identity=identity,
                           rows=rows, row=row, content=content, user=user, message=message,
                           search=search, more=more, menu=menu, back=back, sends=sends, listeners=listeners,
                           add=add, upload=upload, chips=chips, chooser=chooser)


def owned_context(pages, page):
    # new_page counts and supplies the tabs the backend opens through its own CDP window.
    context = SimpleNamespace(pages=pages, new_page=MagicMock(return_value=page))

    @contextmanager
    def expect_page():
        yield SimpleNamespace(value=context.new_page())

    context.expect_page = expect_page
    return context


@pytest.fixture
def run_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(rovo_backend, "time", SimpleNamespace(monotonic=count(step=0.1).__next__))

    def run(target=None, *, existing=(), **kwargs):
        browser = MagicMock(spec=Browser)
        target = target or page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
        browser.contexts = [owned_context([f.page for f in existing], target.page)]
        run.browser = browser
        runtime = MagicMock()
        runtime.__enter__.return_value.chromium.connect_over_cdp.return_value = browser
        monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: runtime)
        result = rovo_backend.operate(ORIGIN, "probe", ACCOUNT, **kwargs)
        if runtime.__enter__.called:
            browser.close.assert_called_once()
        else:
            browser.close.assert_not_called()
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
    result, code = run_browser(target, existing=(closed,))
    assert code == 0, result
    assert result["readiness"] == "authenticated_ui"
    closed.page.get_by_role.assert_not_called()
    target.page.get_by_role.assert_called()


@pytest.mark.parametrize("panels", [[], [False, False], [True, True]])
def test_existing_tabs_do_not_control_owned_tab_selection(run_browser, panels):
    existing = [page_fixture(ORIGIN + f"/jira/boards/{i}", panel_open=opened, draft="User draft")
                for i, opened in enumerate(panels)]
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
    result, code = run_browser(target, existing=existing)
    assert code == 0 and result["tab_selection"] == "connection_owned", result
    target.page.goto.assert_called_once_with(ORIGIN + "/jira/for-you", wait_until="domcontentloaded", timeout=10000)
    target.launcher.click.assert_called_once()
    target.submit.click.assert_not_called()
    for tab in existing:
        assert not tab.page.mock_calls


@pytest.mark.parametrize("url", [
    "https://other.atlassian.net/browse/DEMO-1",
    "https://example.atlassian.net.evil.test/jira/for-you",
    ORIGIN + "/wiki/spaces/DEMO", ORIGIN + "/browse-other/DEMO-1",
])
def test_unrelated_tabs_cannot_be_selected(run_browser, url):
    unrelated = page_fixture(url)
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    result, code = run_browser(target, existing=(unrelated,))
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
    result, code = run_browser(target, existing=(other,), prompt=PROMPT)
    assert code == 1 and "after submission" in result["message"], result
    assert result["submission_state"] == "attempted_unknown" and result["retry_safe"] is False
    target.submit.click.assert_called_once()
    other.submit.click.assert_not_called()
    record = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert record["submission_state"] == "attempted_unknown"
    result, code = rovo_backend.operate(ORIGIN, "another-session", ACCOUNT, prompt=PROMPT)
    assert code == 4 and result["retry_safe"] is False
    target.submit.click.assert_called_once()


def synthetic_pngs(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
    return load_images([tmp_path / name for name in names])


def test_ask_uploads_each_png_in_order(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    images = synthetic_pngs(tmp_path, "first.png", "second.png")
    result, code = run_browser(target, prompt=PROMPT, images=images)
    assert code == 0 and result["image_count"] == 2, result
    assert target.add.click.call_count == 2 and target.upload.click.call_count == 2
    assert [c.args[0]["name"] for c in target.chooser.value.set_files.call_args_list] == ["first.png", "second.png"]
    assert list(target.chips) == ["Remove file first.png", "first PNG", "Remove file second.png", "second PNG"]
    for chip in target.chips.values():
        chip.wait_for.assert_called_once_with(state="visible", timeout=30000)
    target.submit.click.assert_called_once()


def test_unconfirmed_upload_never_submits(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.chips["Remove file first.png"] = MagicMock(spec=Locator)
    target.chips["Remove file first.png"].wait_for.side_effect = TimeoutError("Locator.wait_for: Timeout 30000ms exceeded.")
    result, code = run_browser(target, prompt=PROMPT, images=synthetic_pngs(tmp_path, "first.png"))
    assert code == 1, result
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    target.chooser.value.set_files.assert_called_once()
    target.submit.click.assert_not_called()
    assert not list(tmp_path.rglob("request.json"))


def test_completion_is_awaited_in_page_not_by_polling(run_browser):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer", result
    args = [call.args[1] for call in target.panel.evaluate.call_args_list]
    assert args and all(arg["before"] == 0 and arg["prompt"] == PROMPT and 0 < arg["ms"] <= 1000 for arg in args)
    assert 200 not in [call.args[0] for call in target.page.wait_for_timeout.call_args_list]


@pytest.mark.parametrize("seen", [True, False])
def test_start_seen_only_inside_the_page_wait_still_counts(run_browser, tmp_path, seen):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    target.status.inner_text.side_effect = None
    target.status.inner_text.return_value = "Response complete."
    snapshot = target.panel.evaluate.side_effect
    target.panel.evaluate.side_effect = lambda script, arg=None: snapshot(script, arg) | {"started": seen}
    result, code = run_browser(target, prompt=PROMPT, timeout=1)
    assert (code, result["execution_status"]) == ((0, "completed") if seen else (3, "timeout")), result
    target.submit.click.assert_called_once()


def test_navigation_during_page_wait_keeps_uncertainty(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")

    def navigate(script, arg=None):
        target.page.url = ORIGIN + "/wiki/spaces/DEMO"
        raise Error("Execution context was destroyed, most likely because of a navigation")
    target.panel.evaluate.side_effect = navigate
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "left the expected site after submission" in result["message"], result
    assert result["submission_state"] == "attempted_unknown" and result["retry_safe"] is False
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
    target.launcher.click.assert_not_called()
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


def test_existing_legacy_and_mini_modal_panels_are_untouched(run_browser):
    legacy = page_fixture(ORIGIN + "/jira/for-you")
    mini = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL)
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
    result, code = run_browser(target, existing=(legacy, mini))
    assert code == 0, result
    for existing in (legacy, mini):
        assert not existing.page.mock_calls


@pytest.mark.parametrize("prompt", [None, PROMPT])
def test_mini_modal_wrong_account_is_not_authenticated(run_browser, prompt):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL, authenticated=False)
    result, code = run_browser(target, prompt=prompt)
    assert code == 2 and result["execution_status"] == "authentication_required", result
    target.submit.click.assert_not_called()


def test_missing_panel_wait_is_bounded_and_launcher_is_not_retried(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", panel_open=False)
    target.launcher.click.side_effect = None
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result["readiness_phase"] == "panel", result
    assert "without refresh" in result["message"]
    target.launcher.click.assert_called_once()
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    target.page.reload.assert_not_called()
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


@pytest.mark.parametrize("delayed", ["account", "panel", "composer"])
def test_delayed_readiness_waits_without_refresh_or_duplicate_open(run_browser, delayed):
    from itertools import chain, repeat

    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
    control = {"account": target.identity, "panel": target.panel, "composer": target.textbox}[delayed]
    control.is_visible.side_effect = chain([False, False], repeat(True))
    result, code = run_browser(target)
    assert code == 0 and result["readiness_phase"] == "ready", result
    assert target.page.wait_for_timeout.call_count >= 1
    assert target.launcher.click.call_count <= 1
    target.page.reload.assert_not_called()
    target.submit.click.assert_not_called()


def test_wrong_account_never_opens_rovo(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False, authenticated=False)
    result, code = run_browser(target)
    assert code == 2 and result["readiness_phase"] == "account", result
    target.launcher.click.assert_not_called()
    target.page.reload.assert_not_called()
    target.page.close.assert_not_called()


@pytest.mark.parametrize("panel_open,correct_account", [(False, True), (True, True), (False, False)])
def test_overflow_keeps_launcher_mounted_until_panel_opens(run_browser, panel_open, correct_account):
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=panel_open, authenticated=False)
    more = target.page.get_by_role("button", name="Show more", exact=True)
    menu = {"open": False, "closing": False}
    more.is_visible.return_value = True
    more.click.side_effect = lambda **kw: menu.update(open=True, closing=False)
    target.identity.is_visible.side_effect = lambda: correct_account and menu["open"]
    target.launcher.is_visible.side_effect = lambda: menu["open"] or menu["closing"]

    def escape(key):
        assert key == "Escape"
        menu.update(open=False, closing=True)

    def launch(**kw):
        # The closing popover stays briefly visible, then unmounts its launcher.
        if not menu["open"]:
            raise TimeoutError("Locator.click: Timeout 10000ms exceeded.\n  - element was detached from the DOM, retrying")
        target.panel.is_visible.return_value = True
        menu.update(open=False, closing=False)

    target.page.keyboard.press.side_effect = escape
    target.launcher.click.side_effect = launch
    result, code = run_browser(target)
    assert code == (0 if correct_account else 2), result
    if correct_account:
        assert result["readiness_phase"] == "ready"
    assert target.launcher.click.call_count == int(correct_account and not panel_open)
    more.click.assert_called_once()
    target.page.keyboard.press.assert_called_once_with("Escape")
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    target.page.reload.assert_not_called()


def test_navigation_while_waiting_stops_preparation(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
    target.launcher.click.side_effect = lambda **kw: setattr(target.page, "url", "https://other.atlassian.net/jira/for-you")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "during preparation" in result["message"], result
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    target.page.reload.assert_not_called()
    target.page.close.assert_not_called()


def test_owned_tab_opens_offscreen_in_its_own_background_window(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    assert run_browser(target)[1] == 0
    cdp = run_browser.browser.new_browser_cdp_session.return_value
    calls = [c.args for c in cdp.send.call_args_list]
    assert calls[0] == ("Target.createTarget", {"url": "about:blank", "newWindow": True, "background": True})
    bounds = next(args[1]["bounds"] for args in calls if args[0] == "Browser.setWindowBounds")
    # Minimized pages are hidden and pause animation frames, so clicks would time out.
    assert bounds["left"] < 0 and (bounds["width"], bounds["height"]) == (1440, 900) and "windowState" not in bounds
    cdp.detach.assert_called_once()
    target.page.goto.assert_called_once()


def test_only_verified_empty_owned_legacy_tab_is_closed(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you", empty_chat=True)
    user = page_fixture(ORIGIN + "/browse/DEMO-1", empty_chat=True)
    result, code = run_browser(target, existing=(user,))
    assert code == 0, result
    target.page.close.assert_called_once()
    assert not user.page.mock_calls


@pytest.mark.parametrize("state", ["draft", "attachment", "generating", "response", "mini", "hidden"])
def test_cleanup_preserves_any_nonempty_or_unverified_owned_tab(run_browser, state):
    target = page_fixture(ORIGIN + "/jira/for-you", empty_chat=True,
                          draft="User draft" if state == "draft" else "",
                          layout=MINI_PANEL if state == "mini" else PANEL)
    target.attachments.count.return_value = int(state == "attachment")
    target.stop.is_visible.return_value = state == "generating"
    target.responses.count.return_value = int(state == "response")
    target.textbox.is_visible.return_value = state != "hidden"
    run_browser(target)
    target.page.close.assert_not_called()
    target.page.reload.assert_not_called()


def test_uncertain_send_never_closes_even_an_empty_owned_tab(run_browser, tmp_path):
    target = page_fixture(ORIGIN + "/jira/for-you", empty_chat=True)
    target.submit.click.side_effect = RuntimeError("Connection lost during submit")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result["submission_state"] == "attempted_unknown", result
    target.page.close.assert_not_called()
    target.submit.click.assert_called_once()
    assert read_request(state_dir(tmp_path, ORIGIN, "probe"))["submission_state"] == "attempted_unknown"


def test_cleanup_rechecks_origin_after_pending_navigation_events(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you", empty_chat=True)

    def deliver_navigation():
        target.page.url = "https://other.atlassian.net/jira/for-you"
        return 0

    target.groups.count.side_effect = deliver_navigation
    assert run_browser(target)[1] == 0
    target.page.close.assert_not_called()


CHAT = "12345678-1234-4234-8234-123456789abc"


def history(target, items, more, *, chat=None, cursor=False):
    """Deliver one of Rovo's own paged history responses (list, or one chat's messages) to the tab."""
    path = f"conversation/{chat}/messages" if chat else "conversations?limit=25"
    url = f"{ORIGIN}/gateway/api/assist/rovo/v1/chat/{path}" + (("&" if "?" in path else "?") + "cursor=synthetic" if cursor else "")
    response = SimpleNamespace(url=url, request=SimpleNamespace(method="GET"),
                               json=lambda: {"items": [{}] * items, "cursor": "synthetic" if more else None, "hasNext": more})
    for handler in list(target.listeners.get("response", [])):
        handler(response)


def test_chat_list_scrolls_until_rovo_reports_the_end(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.search.is_visible.return_value = True
    target.rows.count.return_value = 25
    target.rows.evaluate_all.side_effect = None
    target.rows.evaluate_all.return_value = [{"id": CHAT, "title": "Synthetic"}]
    target.page.goto.side_effect = lambda *a, **k: history(target, 25, True)

    def scroll(script, top):
        assert top is False
        history(target, 4, False, cursor=True)
        target.rows.count.return_value = 29
    target.rows.last.evaluate.side_effect = scroll
    result, code = run_browser(target, action="chat_list")
    assert code == 0, result
    assert result["coverage"] == "complete" and result["truncated"] is False
    target.rows.last.evaluate.assert_called_once()
    target.submit.click.assert_not_called()


@pytest.mark.parametrize("seen", ["none", "more", "unrendered"])
def test_chat_list_without_proof_of_the_end_stays_loaded_only(run_browser, seen):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.search.is_visible.return_value = True
    target.rows.count.return_value = 25
    target.rows.evaluate_all.side_effect = None
    target.rows.evaluate_all.return_value = []
    if seen != "none":
        target.page.goto.side_effect = lambda *a, **k: history(target, 29, seen == "more")
    result, code = run_browser(target, action="chat_list")
    assert code == 0 and result["coverage"] == "loaded_only" and result["truncated"] is False, result


def test_chat_list_stops_scrolling_past_the_output_cap(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.search.is_visible.return_value = True
    target.rows.count.return_value = 101
    target.rows.evaluate_all.side_effect = None
    target.rows.evaluate_all.return_value = []
    target.page.goto.side_effect = lambda *a, **k: history(target, 101, True)
    result, code = run_browser(target, action="chat_list")
    assert code == 0 and result["truncated"] is True and result["coverage"] == "loaded_only", result
    target.rows.last.evaluate.assert_not_called()


@pytest.mark.parametrize("ends", [True, False])
def test_chat_export_scrolls_up_until_older_turns_end(run_browser, ends):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.groups.evaluate_all.return_value = [{"user": "Synthetic question", "assistant": "Synthetic answer"}]
    target.row.click.side_effect = lambda **k: history(target, 2, True, chat=CHAT)

    def scroll(script, top):
        assert top is True
        history(target, 4, not ends, chat=CHAT, cursor=True)
        target.groups.count.return_value = 3
    target.groups.first.evaluate.side_effect = scroll
    result, code = run_browser(target, action="chat_export", chat_id=CHAT)
    assert code == 0, result
    assert result["coverage"] == ("complete" if ends else "loaded_only")
    assert result["messages"] == [{"role": "user", "text": "Synthetic question"}, {"role": "assistant", "text": "Synthetic answer"}]
    target.submit.click.assert_not_called()


def browsed(action):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.search.is_visible.return_value = True
    target.rows.evaluate_all.side_effect = None
    target.rows.evaluate_all.return_value = []
    target.rows.count.return_value = 0
    target.groups.evaluate_all.return_value = []
    kwargs = {"action": action, "chat_id": CHAT} if action == "chat_export" else {"action": action}
    return target, kwargs


@pytest.mark.parametrize("action", ["chat_list", "chat_export"])
def test_list_and_export_close_their_idle_owned_tab(run_browser, action):
    target, kwargs = browsed(action)
    assert run_browser(target, **kwargs)[1] == 0
    target.page.close.assert_called_once()


@pytest.mark.parametrize("action", ["chat_list", "chat_export"])
@pytest.mark.parametrize("state", ["draft", "attachment", "generating", "error"])
def test_list_and_export_keep_a_tab_that_holds_work_or_failed(run_browser, action, state):
    target, kwargs = browsed(action)
    def later(script):
        # Work appears after the operation's own idle checks, as if someone used the window meanwhile.
        if state == "error":
            raise RuntimeError("Synthetic read failure")
        {"draft": lambda: setattr(target.textbox.evaluate, "return_value", "Unsent work"),
         "attachment": lambda: setattr(target.attachments.count, "return_value", 1),
         "generating": lambda: setattr(target.stop.is_visible, "return_value", True)}[state]()
        return []
    (target.groups if action == "chat_export" else target.rows).evaluate_all.side_effect = later
    result, code = run_browser(target, **kwargs)
    assert code == (1 if state == "error" else 0), result.get("message")
    target.page.close.assert_not_called()
