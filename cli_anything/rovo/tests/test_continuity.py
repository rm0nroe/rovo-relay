"""Automatic continuation must bind verified history, never picker order or titles."""
import json
from types import SimpleNamespace

import pytest

from cli_anything.rovo import rovo_cli
from cli_anything.rovo.core.state import next_action, read_request, save_request, site_lock, state_dir
from cli_anything.rovo.utils import rovo_backend
from test_browser_tabs import ACCOUNT, ORIGIN, PROMPT, page_fixture, run_browser

CHAT = "12345678-1234-4234-8234-123456789abc"
OTHER = "22345678-1234-4234-8234-123456789abc"


def completed(run_browser):
    result, code = run_browser(prompt=PROMPT)
    assert code == 0 and result["continuity_status"] == "verified", result
    assert result["chat_id"] == CHAT and next_action(result, code) == "ask"
    assert set(result["timings_ms"]) == {"attach", "prepare", "select", "generate", "capture"}
    return result


def existing():
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.responses.count.return_value = 1
    target.groups.count.return_value = 1
    return target


def test_new_chat_binding_survives_restart_and_followup(run_browser, tmp_path):
    completed(run_browser)
    target = existing()
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["conversation_mode"] == "continued", result
    assert result["chat_id"] == CHAT and result["turn_count"] == 2
    assert result["chat_selection"] == "picker"
    target.new_chat.click.assert_not_called()
    target.row.click.assert_called_once()
    target.submit.click.assert_called_once()
    stored = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert stored["turn_sha256"] == result["turn_sha256"]
    assert PROMPT not in json.dumps(stored) and "Synthetic answer" not in json.dumps(stored)


@pytest.mark.parametrize("change", ["user", "answer", "count"])
def test_changed_saved_history_stops_before_fill(run_browser, change):
    completed(run_browser)
    target = existing()
    if change == "user":
        target.user.inner_text.return_value = "Another task"
    elif change == "answer":
        target.content.all_inner_texts.return_value = ["Different response"]
    else:
        target.groups.count.return_value = 2
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "changed" in result["message"], result
    assert result["error_code"] == "conversation_changed" and next_action(result, code) == "new_or_inspect"
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()


@pytest.mark.parametrize("change", [{"account": "other@example.com"}, {"site": "https://other.atlassian.net"},
                                    {"chat_id": None}, {"continuity_status": "unavailable"},
                                    {"chat_id": "bad-id"}])
def test_invalid_binding_never_attaches(run_browser, tmp_path, change):
    completed(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    with site_lock(directory):
        save_request(directory, read_request(directory) | change)
    target = existing()
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result["submission_state"] == "not_attempted", result
    assert result["error_code"] == "continuity_unbound" and next_action(result, code) == "new_or_inspect"
    target.page.goto.assert_not_called()
    target.submit.click.assert_not_called()


@pytest.mark.parametrize("ids", [[], [CHAT, OTHER], ["not-a-uuid"]])
def test_capture_failure_preserves_answer_and_blocks_implicit_followup(run_browser, tmp_path, ids):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.sends[:] = ids
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer", result
    assert result["continuity_status"] == "unavailable" and result["retry_safe"] is False
    assert next_action(result, code) == "new_or_inspect"
    assert read_request(state_dir(tmp_path, ORIGIN, "probe"))["execution_status"] == "completed"
    assert run_browser(prompt=PROMPT)[1] == 1
    target.submit.click.assert_called_once()
    target.page.close.assert_not_called()


def test_verified_answer_tab_closes_at_exit(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    completed(lambda **kwargs: run_browser(target, **kwargs))
    target.page.close.assert_called_once()


def test_new_chat_binds_from_send_request_without_picker(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    completed(lambda **kwargs: run_browser(target, **kwargs))
    target.menu.click.assert_not_called()
    target.back.click.assert_not_called()
    target.row.click.assert_not_called()
    target.rows.evaluate_all.assert_not_called()
    assert target.listeners["request"] == []


def test_send_request_from_another_site_is_ignored(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    send = target.submit.click.side_effect
    def other_site():
        send()
        request = SimpleNamespace(method="POST", url=f"https://other.atlassian.net/gateway/api/assist/rovo/v1/chat/conversation/{OTHER}/message/stream/sse")
        target.listeners["request"][0](request)
    target.submit.click.side_effect = other_site
    assert completed(lambda **kwargs: run_browser(target, **kwargs))["chat_id"] == CHAT


def test_completed_turn_changed_before_capture_is_not_bound(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.content.all_inner_texts.side_effect = [["Synthetic answer"]] * 2 + [["Different response"]] * 9
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["continuity_status"] == "unavailable", result
    assert result["chat_id"] is None


def test_new_replaces_binding_and_explicit_chat_adopts_binding(run_browser):
    completed(run_browser)
    target = page_fixture(ORIGIN + "/jira/for-you")
    result, code = run_browser(target, prompt=PROMPT, new=True)
    assert code == 0 and result["conversation_mode"] == "new", result
    target.new_chat.click.assert_called_once()
    target = existing()
    target.user.inner_text.return_value = "Different prior question"
    target.submit.click.side_effect = lambda: (setattr(target.user.inner_text, "return_value", PROMPT),
                                               setattr(target.responses.count, "return_value", 2),
                                               setattr(target.groups.count, "return_value", 2))
    result, code = run_browser(target, prompt=PROMPT, chat_id=CHAT)
    assert code == 0 and result["continuity_status"] == "verified", result
    target.new_chat.click.assert_not_called()


def test_new_does_not_bypass_uncertain_delivery(run_browser, tmp_path):
    completed(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    with site_lock(directory):
        save_request(directory, read_request(directory) | {"execution_status": "timeout"})
    target = existing()
    result, code = run_browser(target, prompt=PROMPT, new=True)
    assert code == 4, result
    target.page.goto.assert_not_called()
    target.submit.click.assert_not_called()


def test_new_and_chat_are_mutually_exclusive(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    result, code = rovo_cli.invoke(["--site", ORIGIN, "--session", "probe", "--account", ACCOUNT,
                                  "--dry-run", "ask", "--new", "--chat", CHAT, "--prompt-file", str(prompt)])
    assert code == 1 and "either" in result["message"]


def test_missing_saved_row_preserves_binding_without_sending(run_browser, tmp_path):
    completed(run_browser)
    before = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    target = existing()
    target.row.wait_for.side_effect = ValueError("Saved conversation unavailable")
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and result["submission_state"] == "not_attempted", result
    target.submit.click.assert_not_called()
    assert read_request(state_dir(tmp_path, ORIGIN, "probe")) == before


def test_new_binding_is_isolated_by_session(run_browser, tmp_path, monkeypatch):
    completed(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    directory.rename(directory.with_name("other-session"))
    result, code = run_browser(prompt=PROMPT)
    assert code == 0 and result["conversation_mode"] == "new", result


def test_changed_conversation_while_filling_never_submits(run_browser):
    completed(run_browser)
    target = existing()
    fill = target.textbox.fill.side_effect
    def change(text):
        fill(text)
        target.user.inner_text.return_value = "Different chat selected during fill"
    target.textbox.fill.side_effect = change
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "changed before submission" in result["message"], result
    target.submit.click.assert_not_called()


def count_reads(monkeypatch):
    """Count idle checks and signature reads; the real functions still run."""
    calls = {"require_idle": 0, "turn_signature": 0}
    for name in calls:
        def spy(*args, _name=name, _real=getattr(rovo_backend, name)):
            calls[_name] += 1
            return _real(*args)
        monkeypatch.setattr(rovo_backend, name, spy)
    return calls


def test_automatic_picker_followup_reuses_verified_reads(run_browser, monkeypatch):
    completed(run_browser)
    calls = count_reads(monkeypatch)
    result, code = run_browser(existing(), prompt=PROMPT)
    assert code == 0 and result["chat_selection"] == "picker", result
    # Before selection, at the end of opening the chat; history check, post-fill check, capture.
    # Exit cleanup adds one of each after the answer is returned.
    assert calls == {"require_idle": 3, "turn_signature": 4}


def test_explicit_chat_skips_repeat_idle_check(run_browser, monkeypatch):
    target = existing()
    target.submit.click.side_effect = lambda: (setattr(target.responses.count, "return_value", 2),
                                               setattr(target.groups.count, "return_value", 2))
    calls = count_reads(monkeypatch)
    result, code = run_browser(target, prompt=PROMPT, chat_id=CHAT)
    assert code == 0 and result["continuity_status"] == "verified", result
    assert calls == {"require_idle": 3, "turn_signature": 4}  # includes exit cleanup


@pytest.mark.parametrize("click", [True, False])
def test_new_chat_rechecks_idle_only_after_a_click(run_browser, monkeypatch, click):
    target = page_fixture(ORIGIN + "/jira/for-you", empty_chat=not click)
    target.new_chat.is_enabled.return_value = click
    calls = count_reads(monkeypatch)
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["answer"] == "Synthetic answer", result
    assert calls == {"require_idle": 3 if click else 2, "turn_signature": 2}  # includes exit cleanup


def test_draft_appearing_after_new_chat_click_is_still_blocked(run_browser):
    target = page_fixture(ORIGIN + "/jira/for-you")
    clear = target.new_chat.click.side_effect
    target.new_chat.click.side_effect = lambda: (clear(), setattr(target.textbox.evaluate, "return_value", "Unsent work"))
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 1 and "Existing draft" in result["message"], result
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()


def test_saved_row_below_loaded_history_is_scrolled_into_view(run_browser):
    completed(run_browser)
    target = existing()
    target.search.is_visible.return_value = True
    target.row.is_visible.return_value = False

    def scroll(script, top):
        assert top is False
        target.row.is_visible.return_value = True
    target.rows.last.evaluate.side_effect = scroll
    result, code = run_browser(target, prompt=PROMPT)
    assert code == 0 and result["chat_selection"] == "picker", result
    target.rows.last.evaluate.assert_called_once()
    target.row.click.assert_called_once()
