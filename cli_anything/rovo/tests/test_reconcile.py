"""Reconcile lifts an uncertain-delivery block only on proof from Rovo's own message data; it never sends."""
from hashlib import sha256
from itertools import repeat

import pytest

from cli_anything.rovo import rovo_cli
from cli_anything.rovo.core.state import delivered, next_action, read_request, save_request, site_lock, state_dir
from test_browser_tabs import ACCOUNT, ORIGIN, PROMPT, history, page_fixture, run_browser, turns

CHAT = "12345678-1234-4234-8234-123456789abc"


def timed_out(run_browser):
    """A real new-chat ask that times out after its one send, leaving the site blocked."""
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.status.inner_text.side_effect = repeat("Rovo is thinking")
    result, code = run_browser(target, prompt=PROMPT, timeout=1)
    assert code == 3 and result["execution_status"] == "timeout", result
    return result


def reopened(items, more=False):
    target = page_fixture(ORIGIN + "/jira/for-you")
    target.row.click.side_effect = lambda **k: history(target, items, more, chat=CHAT)
    return target


def test_timeout_records_what_reconcile_needs(run_browser, tmp_path):
    timed_out(run_browser)
    stored = read_request(state_dir(tmp_path, ORIGIN, "probe"))
    assert stored["submission_state"] == "attempted_unknown"
    assert stored["chat_id"] == CHAT and stored["turns_before"] == 0
    assert stored["prompt_sha256"] == sha256(PROMPT.encode()).hexdigest()
    assert PROMPT not in str(stored)


def test_blocked_result_points_at_reconcile(run_browser):
    timed_out(run_browser)
    result, code = run_browser(prompt=PROMPT)
    assert code == 4 and result["reconcilable"] is True, result
    assert next_action(result, code) == "reconcile"


def test_another_sessions_block_is_not_reconcilable_here(run_browser, tmp_path):
    timed_out(run_browser)
    other = state_dir(tmp_path, ORIGIN, "other")
    with site_lock(other):
        save_request(other, {"submission_state": "not_attempted", "execution_status": "prepared"})
    from cli_anything.rovo.utils import rovo_backend
    result, code = rovo_backend.operate(ORIGIN, "other", ACCOUNT, prompt=PROMPT)
    assert code == 4 and result["reconcilable"] is False and next_action(result, code) == "stop"


def test_proof_lifts_the_block_without_sending(run_browser, tmp_path):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    original = read_request(directory)
    target = reopened(turns(PROMPT, "Late answer"))
    result, code = run_browser(target, action="reconcile")
    assert code == 0 and result["answer"] == "Late answer", result
    assert next_action(result, code) == "new_or_inspect"
    target.submit.click.assert_not_called()
    target.textbox.fill.assert_not_called()
    stored = read_request(directory)
    assert (stored["execution_status"], stored["submission_state"], stored["continuity_status"]) == (
        "completed", "observed_submitted", "unavailable")
    assert stored["reconciled"] == {"evidence": "rovo_messages", "message_id": "id-Late answer", "original": original}
    # The site is no longer blocked.
    assert run_browser(page_fixture(ORIGIN + "/jira/for-you"))[1] == 0


@pytest.mark.parametrize("items,more,reason", [
    (turns("Another question", "Another answer"), False, "prompt_missing"),
    (turns(PROMPT, "First", PROMPT, "Second"), False, "prompt_duplicated"),
    (turns(PROMPT, "")[:1], False, "answer_missing"),
    (turns(PROMPT, ""), False, "answer_missing"),
    (turns(PROMPT, "Late answer"), True, "history_incomplete"),
])
def test_anything_short_of_proof_changes_nothing(run_browser, tmp_path, items, more, reason):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    before = (directory / "request.json").read_bytes()
    target = reopened(items, more)
    result, code = run_browser(target, action="reconcile")
    assert code == 4 and result["reconcile_reason"] == reason, result
    assert result["reconcilable"] is False and next_action(result, code) == "stop"
    assert (directory / "request.json").read_bytes() == before
    target.submit.click.assert_not_called()


def test_missing_rovo_data_changes_nothing(run_browser, tmp_path):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    before = (directory / "request.json").read_bytes()
    result, code = run_browser(page_fixture(ORIGIN + "/jira/for-you"), action="reconcile")
    assert code == 4 and result["reconcile_reason"] == "history_incomplete", result
    assert (directory / "request.json").read_bytes() == before


@pytest.mark.parametrize("change", [{"prompt_sha256": None}, {"chat_id": None}, {"turns_before": None}])
def test_record_without_proof_fields_refuses_before_attaching(run_browser, tmp_path, change):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    with site_lock(directory):
        save_request(directory, read_request(directory) | change)
    target = reopened(turns(PROMPT, "Late answer"))
    result, code = run_browser(target, action="reconcile")
    assert code == 4 and result["reconcile_reason"] == "record_unprovable", result
    target.page.goto.assert_not_called()


def test_blocked_ask_without_proof_fields_stops(run_browser, tmp_path):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    with site_lock(directory):
        save_request(directory, read_request(directory) | {"prompt_sha256": None})
    result, code = run_browser(prompt=PROMPT)
    assert code == 4 and result["reconcilable"] is False and next_action(result, code) == "stop"


@pytest.mark.parametrize("record", [None, {"submission_state": "observed_submitted", "execution_status": "completed"}])
def test_nothing_to_reconcile_never_attaches(run_browser, tmp_path, record):
    directory = state_dir(tmp_path, ORIGIN, "probe")
    if record:
        with site_lock(directory):
            save_request(directory, record)
    target = page_fixture(ORIGIN + "/jira/for-you")
    result, code = run_browser(target, action="reconcile")
    assert code == 1 and result["error_code"] == "reconcile_not_needed", result
    assert next_action(result, code) == "stop"
    target.page.goto.assert_not_called()


def test_generation_still_running_keeps_the_block(run_browser, tmp_path):
    timed_out(run_browser)
    directory = state_dir(tmp_path, ORIGIN, "probe")
    before = (directory / "request.json").read_bytes()
    target = reopened(turns(PROMPT, "Partial"))
    target.stop.is_visible.return_value = True
    result, code = run_browser(target, action="reconcile")
    assert code == 1 and result["retry_safe"] is False and next_action(result, code) == "stop", result
    assert (directory / "request.json").read_bytes() == before


HASH = sha256(b"Q").hexdigest()


def messages(*texts):
    return [{"id": "id-" + str(n), "role": "HUMAN" if n % 2 == 0 else "ASSISTANT", "text": text}
            for n, text in enumerate(texts)]


@pytest.mark.parametrize("texts,before,expected", [
    (("Q", "A"), 0, ("id-1", None)),
    # The same question asked before the attempt is not this attempt.
    (("Q", "Old", "Q", "New"), 1, ("id-3", None)),
    (("Q", "Old", "Other", "A"), 1, (None, "prompt_missing")),
    (("Q", "A"), 1, (None, "prompt_missing")),
    (("Q", "A", "Q", "B"), 0, (None, "prompt_duplicated")),
    (("Q",), 0, (None, "answer_missing")),
    (("Q", "  "), 0, (None, "answer_missing")),
    # A human follow-up typed later does not answer the attempt.
    (("Q", "A", "Later", "B"), 0, ("id-1", None)),
])
def test_delivered_rule(texts, before, expected):
    reply, reason = delivered(messages(*texts), HASH, before)
    assert ((reply or {}).get("id"), reason) == expected


def test_reconcile_dry_run_touches_nothing(tmp_path):
    result, code = rovo_cli.invoke(["--site", ORIGIN, "--session", "probe", "--account", ACCOUNT, "--dry-run", "reconcile"])
    assert code == 0 and result["dry_run"] is True and result["action"] == "reconcile"


def test_signed_out_reconcile_keeps_the_attempt_unsafe(run_browser):
    timed_out(run_browser)
    result, code = run_browser(page_fixture(ORIGIN + "/jira/for-you", authenticated=False), action="reconcile")
    assert code == 2 and result["retry_safe"] is False and next_action(result, code) == "stop", result
