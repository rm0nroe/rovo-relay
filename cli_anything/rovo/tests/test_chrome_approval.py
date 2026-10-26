"""Approval ownership and fail-closed attachment; no real browser or clicks."""
from itertools import chain, repeat
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cli_anything.rovo.utils import chrome_approval as approval, rovo_backend
from cli_anything.rovo import rovo_cli
from test_session import FLAGS, browser_env, stream


ROWS = [(10, "127.0.0.1:9222->127.0.0.1:50000"), (30, "127.0.0.1:50000->127.0.0.1:9222")]
DIALOG = (100, 10, 100, 200, 400, 200)


@pytest.mark.parametrize("rows,parents,expected", [
    (ROWS, {30: 20, 20: 1}, True),
    (ROWS, {30: 99}, False),
    (ROWS, {30: 31, 31: 30}, False),
    (ROWS + [(40, "127.0.0.1:50001->127.0.0.1:9222")], {30: 20}, False),
    (ROWS[:1], {30: 20}, False),
    ([(11, ROWS[0][1]), ROWS[1]], {30: 20}, False),
])
def test_socket_requires_one_complete_owned_loopback_pair(rows, parents, expected):
    assert approval.owned_socket(rows, 9222, 10, 20, parents) is expected


@pytest.mark.parametrize("dialogs", [[], [DIALOG, (101, *DIALOG[1:])], [(101, *DIALOG[1:])],
                                     [(100, 11, *DIALOG[2:])], [(100, 10, 101, *DIALOG[3:])]])
def test_changed_or_ambiguous_dialog_is_never_accepted(dialogs):
    with pytest.raises(approval.GuardFailure):
        approval.one_dialog(dialogs, 10, DIALOG)


def sheets(*dialogs):
    """FIND_DIALOGS output: parent window bounds, then the sheet's position and size."""
    return "\n".join(f"{d['window']} {d['x']} {d['y']} {d['w']} {d['h']}" for d in dialogs)


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setattr(approval.select, "select", lambda *a: ([], [], []))
    monkeypatch.setattr(approval.time, "sleep", lambda *a: None)
    calls = []
    dialog = {"window": "0,25,1440,875", "x": 100, "y": 200, "w": 400, "h": 200}
    native = SimpleNamespace(calls=calls, dialog=dialog, found=iter([[], [dialog], [dialog], [dialog], []]))

    def command(args):
        calls.append(args)
        if args[0] == "/bin/ps":
            return "30 20\n20 1" if "-axo" in args else "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if args[:3] == ["/usr/bin/osascript", "-e", approval.FIND_DIALOGS]:
            assert args[3] == "10"  # only the verified Chrome process is inspected
            return sheets(*next(native.found))
        return "pressed" if args[0] == "/usr/bin/osascript" else ""

    monkeypatch.setattr(approval, "command", command)
    established = chain([[]], repeat(ROWS))
    monkeypatch.setattr(approval, "sockets", lambda p, state:
                        [(10, "127.0.0.1:9222")] if state == "LISTEN" else next(established))
    native.presses = lambda: [c for c in calls if c[:3] == ["/usr/bin/osascript", "-e", approval.PRESS_ALLOW]]
    return native


def test_native_sequence_presses_allow_once_without_pointer_or_focus(native, capsys):
    approval.worker(20, 9222)
    assert json.loads(capsys.readouterr().out) == {"status": "ready"}
    # One Accessibility press of Allow in Chrome's own process: no pointer, no app activation.
    assert len(native.presses()) == 1 and native.presses()[0][-1] == "10"
    assert not any("cliclick" in c[0] or "activate" in " ".join(c) or "frontmost" in " ".join(c) for c in native.calls)


def test_preexisting_second_agent_prompt_is_untouched(native, capsys):
    native.found = iter([[native.dialog]])
    with pytest.raises(approval.GuardFailure, match="busy"):
        approval.worker(20, 9222)
    assert capsys.readouterr().out == ""  # never authorizes attach
    assert native.presses() == []


def test_second_agent_arriving_before_press_is_untouched(native):
    other = native.dialog | {"window": "1440,25,1440,875"}
    native.found = iter([[], [native.dialog], [native.dialog], [native.dialog, other]])
    with pytest.raises(approval.GuardFailure):
        approval.worker(20, 9222)
    assert native.presses() == []


def test_foreign_socket_stops_before_press(native, monkeypatch):
    rows = iter([[], ROWS, ROWS])
    monkeypatch.setattr(approval, "sockets", lambda p, state:
                        [(10, "127.0.0.1:9222")] if state == "LISTEN" else next(rows))
    original = approval.command
    monkeypatch.setattr(approval, "command", lambda args: "30 99" if "-axo" in args else original(args))
    with pytest.raises(approval.GuardFailure, match="busy"):
        approval.worker(20, 9222)
    assert native.presses() == []


def test_dialog_still_open_after_press_does_not_report_success(native):
    native.found = iter([[], [native.dialog], [native.dialog], [native.dialog], [native.dialog]])
    with pytest.raises(approval.GuardFailure, match="changed"):
        approval.worker(20, 9222)
    assert len(native.presses()) == 1


def test_allow_not_found_by_accessibility_is_not_success(native, monkeypatch):
    original = approval.command
    monkeypatch.setattr(approval, "command", lambda args: "not found" if args[2:3] == [approval.PRESS_ALLOW] else original(args))
    with pytest.raises(approval.GuardFailure, match="changed"):
        approval.worker(20, 9222)


@pytest.fixture
def helper(monkeypatch):
    helper = MagicMock()
    helper.failure.return_value = None
    monkeypatch.setattr(rovo_backend, "ChromeApproval", lambda port: helper)
    return helper


def test_opt_in_approves_once_for_retained_session(browser_env, helper, monkeypatch, capsys):
    def connect(*args, **kwargs):
        helper.start.assert_called_once()
        helper.finish.assert_not_called()
        return browser_env.browser
    browser_env.connect.side_effect = connect
    code, results = stream(monkeypatch, capsys, [["status"]], "--chrome-port", "9222", "--approve-chrome-prompt")
    assert code == 0 and len(results) == 2
    helper.finish.assert_called_once()
    helper.close.assert_called_once()
    browser_env.connect.assert_called_once()


@pytest.mark.parametrize("failure", ["start", "finish", "attach"])
def test_approval_failure_is_terminal_and_never_submits(browser_env, helper, monkeypatch, capsys, failure, tmp_path):
    error = approval.ApprovalError("Chrome approval helper failed; nothing was submitted.")
    if failure == "attach":
        browser_env.connect.side_effect = RuntimeError("private socket detail")
        helper.failure.return_value = error
    else:
        getattr(helper, failure).side_effect = error
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Synthetic question")
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)]],
                           "--chrome-port", "9222", "--approve-chrome-prompt")
    assert code == 1 and len(results) == 1
    assert results[0]["error_code"] == "chrome_approval_failed"
    assert results[0]["submission_state"] == "not_attempted" and results[0]["retry_safe"] is True
    assert results[0]["next"] == "stop"
    browser_env.target.submit.click.assert_not_called()
    browser_env.browser.contexts[0].new_page.assert_not_called()
    helper.close.assert_called_once()
    if failure == "start":
        browser_env.connect.assert_not_called()


def test_manual_default_never_runs_helper(browser_env, helper, capsys):
    assert rovo_cli.run([*FLAGS, "status"]) == 0
    helper.start.assert_not_called()


def test_dry_run_never_runs_helper(browser_env, helper, capsys):
    assert rovo_cli.run([*FLAGS, "--approve-chrome-prompt", "--dry-run", "session"]) == 0
    helper.start.assert_not_called()
    browser_env.connect.assert_not_called()


def test_helper_failure_output_is_sanitized():
    with pytest.raises(approval.ApprovalError, match="helper failed") as error:
        approval.ChromeApproval._result('{"status":"error","reason":"/private/secret"}', "approved")
    assert "/private" not in str(error.value)


def test_missing_port_fails_before_starting_helper(monkeypatch):
    monkeypatch.setattr(approval.sys, "platform", "darwin")
    popen = MagicMock()
    monkeypatch.setattr(approval.subprocess, "Popen", popen)
    with pytest.raises(approval.ApprovalError, match="verified --chrome-port"):
        approval.ChromeApproval(None).start()
    popen.assert_not_called()


def test_missing_accessibility_never_signals_ready_or_presses(native, monkeypatch, capsys):
    original = approval.command

    def denied(args):
        if args[2:3] == [approval.FIND_DIALOGS]:
            raise approval.GuardFailure("dependencies")  # osascript exits nonzero without Accessibility
        return original(args)
    monkeypatch.setattr(approval, "command", denied)
    with pytest.raises(approval.GuardFailure, match="dependencies"):
        approval.worker(20, 9222)
    assert capsys.readouterr().out == "" and native.presses() == []


def test_helper_runs_on_this_python_without_quartz(monkeypatch):
    monkeypatch.setattr(approval.sys, "platform", "darwin")
    popen = MagicMock()
    popen.return_value.stdout.readline.return_value = '{"status": "ready"}'
    monkeypatch.setattr(approval.subprocess, "Popen", popen)
    monkeypatch.setattr(approval.select, "select", lambda r, *a: (r, [], []))
    approval.ChromeApproval(9222).start()
    args = popen.call_args.args[0]
    assert args[0] == sys.executable and args[-3].endswith("chrome_approval.py")
    assert "import Quartz" not in open(approval.__file__).read()


def test_no_dialog_times_out_without_click(native, monkeypatch):
    native.found = repeat([])
    monkeypatch.setattr(approval.time, "monotonic", iter([0, 18]).__next__)
    with pytest.raises(approval.GuardFailure, match="timeout"):
        approval.worker(20, 9222)
    assert native.presses() == []


def test_unresolved_delivery_blocks_before_helper(browser_env, helper, monkeypatch, capsys, tmp_path):
    from cli_anything.rovo.core.state import save_request, state_dir
    from test_browser_tabs import ORIGIN, ACCOUNT
    directory = state_dir(tmp_path, ORIGIN, "other")
    directory.mkdir(parents=True)
    save_request(directory, {"site": ORIGIN, "account": ACCOUNT, "submission_state": "attempted_unknown",
                             "execution_status": "error"})
    code, results = stream(monkeypatch, capsys, [], "--chrome-port", "9222", "--approve-chrome-prompt")
    assert code == 4 and results[0]["retry_safe"] is False
    helper.start.assert_not_called()
    browser_env.connect.assert_not_called()


def test_pending_helper_is_cancelled_even_after_connect_error(browser_env, helper, monkeypatch, capsys):
    browser_env.connect.side_effect = RuntimeError("connection refused")
    code, results = stream(monkeypatch, capsys, [], "--chrome-port", "9222", "--approve-chrome-prompt")
    assert code == 1 and results[0]["error_code"] == "chrome_connection_failed"
    assert results[0]["retry_safe"] is True and results[0]["next"] == "stop"
    helper.close.assert_called_once()


def test_nonzero_helper_exit_blocks_even_with_success_output(monkeypatch):
    helper = approval.ChromeApproval(9222)
    helper.process = MagicMock(returncode=1)
    helper.process.communicate.return_value = (b'{"status":"approved"}', None)
    with pytest.raises(approval.ApprovalError, match="helper failed"):
        helper.finish()


def test_same_sheet_can_settle_before_the_press(native):
    moved = native.dialog | {"y": 217}
    native.found = iter([[], [native.dialog], [moved], [moved], []])
    approval.worker(20, 9222)
    assert len(native.presses()) == 1


@pytest.mark.parametrize("late", [1, 2])
def test_replacement_or_moved_sheet_before_the_press_is_never_pressed(native, late):
    replacement = native.dialog | {"window": "1440,25,1440,875"}
    moved = native.dialog | {"y": 217}
    native.found = iter(
        [[], [native.dialog], [replacement]] if late == 1 else [[], [native.dialog], [native.dialog], [moved]])
    with pytest.raises(approval.GuardFailure, match="changed"):
        approval.worker(20, 9222)
    assert native.presses() == []
