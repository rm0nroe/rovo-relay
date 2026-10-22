"""Persistent foreground sessions, using only synthetic browser-boundary doubles."""
import io
import json
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Browser, Error

from cli_anything.rovo import rovo_cli
from cli_anything.rovo.core.state import read_request, save_request, site_lock, state_dir
from cli_anything.rovo.utils import rovo_backend
from test_browser_tabs import ACCOUNT, MINI_PANEL, ORIGIN, PROMPT, page_fixture

FLAGS = ["--site", ORIGIN, "--session", "pilot", "--account", ACCOUNT]


@pytest.fixture
def browser_env(monkeypatch, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    browser = MagicMock(spec=Browser)
    browser.contexts = [SimpleNamespace(pages=[target.page])]
    browser.is_connected.return_value = True
    runtime = MagicMock()
    connect = runtime.__enter__.return_value.chromium.connect_over_cdp
    connect.return_value = browser
    monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: runtime)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return SimpleNamespace(target=target, browser=browser, runtime=runtime, connect=connect)


def stream(monkeypatch, capsys, lines, *flags):
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(line) + "\n" for line in lines)))
    code = rovo_cli.run([*FLAGS, *flags, "session"])
    output = capsys.readouterr()
    return code, [json.loads(line) for line in output.out.splitlines()]


def test_stream_reuses_connection_and_rechecks_account(browser_env, monkeypatch, capsys):
    env = browser_env
    identity = env.target.page.get_by_role("button", name=ACCOUNT, exact=True)
    identity.is_visible.side_effect = [True, True, False]
    code, results = stream(monkeypatch, capsys, [["status"], ["status"]])
    assert code == 2 and [r["exit_code"] for r in results] == [0, 0, 2]
    assert results[-1]["execution_status"] == "authentication_required"
    env.connect.assert_called_once_with("chrome", timeout=20000, no_defaults=True)
    env.browser.close.assert_called_once()
    env.runtime.__exit__.assert_called_once()
    env.target.submit.click.assert_not_called()


def test_explicit_chrome_port_reuses_one_loopback_attachment(browser_env, monkeypatch, capsys):
    code, results = stream(monkeypatch, capsys, [["status"]], "--chrome-port", "9222")
    assert code == 0 and [r["exit_code"] for r in results] == [0, 0]
    browser_env.connect.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser", timeout=20000, no_defaults=True)
    browser_env.browser.close.assert_called_once()
    browser_env.target.submit.click.assert_not_called()


def test_one_shot_honors_explicit_chrome_port(browser_env, capsys):
    assert rovo_cli.run([*FLAGS, "--chrome-port", "9333", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["execution_status"] == "completed"
    browser_env.connect.assert_called_once_with("ws://127.0.0.1:9333/devtools/browser", timeout=20000, no_defaults=True)
    browser_env.browser.close.assert_called_once()


@pytest.mark.parametrize("port", ["0", "65536", "-1", "ws://other.example:9222", "9222/escape"])
def test_invalid_explicit_chrome_port_is_rejected_before_attachment(browser_env, capsys, port):
    assert rovo_cli.run([*FLAGS, "--chrome-port", port, "status"]) == 1
    assert json.loads(capsys.readouterr().out)["submission_state"] == "not_attempted"
    browser_env.connect.assert_not_called()


def test_explicit_port_dry_run_never_attaches(browser_env, monkeypatch, capsys):
    code, results = stream(monkeypatch, capsys, [], "--chrome-port", "9222", "--dry-run")
    assert code == 0 and len(results) == 1 and results[0]["dry_run"] is True
    browser_env.runtime.__enter__.assert_not_called()


def test_stream_cannot_change_explicit_port(browser_env, monkeypatch, capsys):
    code, results = stream(monkeypatch, capsys, [["--chrome-port", "9333", "status"], ["status"]], "--chrome-port", "9222")
    assert code == 0 and [r["exit_code"] for r in results] == [0, 1, 0]
    browser_env.connect.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser", timeout=20000, no_defaults=True)


def test_explicit_port_failure_does_not_fall_back_to_another_endpoint(browser_env, monkeypatch, capsys):
    browser_env.connect.side_effect = Error("Synthetic connection failure")
    code, results = stream(monkeypatch, capsys, [["status"]], "--chrome-port", "9222")
    assert code == 1 and len(results) == 1 and results[0]["error_code"] == "chrome_connection_failed"
    browser_env.connect.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser", timeout=20000, no_defaults=True)


def test_repl_retains_explicit_port_and_rejects_changing_it(browser_env, monkeypatch, capsys):
    from cli_anything.rovo.utils import repl_skin

    skin = MagicMock()
    skin.get_input.side_effect = [" ".join([*FLAGS, "status"]),
                                 " ".join([*FLAGS, "--chrome-port", "9333", "status"]), "exit"]
    monkeypatch.setattr(repl_skin, "ReplSkin", lambda *args, **kwargs: skin)
    rovo_cli.repl(9222)
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(results) == 2 and results[0]["execution_status"] == "completed"
    assert results[1]["execution_status"] == "error" and results[1]["submission_state"] == "not_attempted"
    browser_env.connect.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser", timeout=20000, no_defaults=True)
    browser_env.browser.close.assert_called_once()


def test_startup_is_flushed_before_input_and_lock_released(browser_env, monkeypatch, tmp_path):
    class Output(io.StringIO):
        flushed = False

        def flush(self):
            self.flushed = True

    output = Output()

    class Input:
        def readline(self):
            assert output.flushed
            assert json.loads(output.getvalue())["exit_code"] == 0
            assert not list(tmp_path.rglob("control.lock"))
            # Another session can reserve the site while the foreground process is idle.
            with site_lock(state_dir(tmp_path, ORIGIN, "other")):
                pass
            return ""

    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stdin", Input())
    assert rovo_cli.run([*FLAGS, "session"]) == 0
    browser_env.browser.close.assert_called_once()


def test_each_operation_reselects_tabs_but_never_reconnects(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        first, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 0, first
        second = page_fixture(ORIGIN + "/jira/for-you", layout=MINI_PANEL)
        env.browser.contexts[0].pages = [second.page]
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 0 and result["readiness"] == "authenticated_ui_read_only"
        env.browser.close.assert_not_called()
    env.connect.assert_called_once()
    env.browser.close.assert_called_once()


def test_one_shot_still_detaches_each_time(browser_env):
    for _ in range(2):
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT)
        assert code == 0, result
    assert browser_env.connect.call_count == 2
    assert browser_env.browser.close.call_count == 2


def test_cross_session_block_precedes_attachment(browser_env, monkeypatch, capsys, tmp_path):
    directory = state_dir(tmp_path, ORIGIN, "other")
    with site_lock(directory):
        save_request(directory, {"submission_state": "attempted_unknown", "execution_status": "waiting"})
    code, results = stream(monkeypatch, capsys, [["status"]])
    assert code == 4 and len(results) == 1 and results[0]["exit_code"] == 4
    browser_env.runtime.__enter__.assert_not_called()
    browser_env.connect.assert_not_called()
    assert not list(tmp_path.rglob("control.lock"))


@pytest.mark.parametrize("error, expected", [
    ("Could not connect to chrome.\n/private/profile/secret", "chrome_connection_failed"),
    ("DevToolsActivePort file not found at /private/profile/secret", "chrome_debugging_unavailable"),
])
def test_startup_connection_failure_is_terminal_and_sanitized(browser_env, monkeypatch, capsys, error, expected):
    browser_env.connect.side_effect = Error(error)
    code, results = stream(monkeypatch, capsys, [["status"]])
    assert code == 1 and len(results) == 1 and results[0]["exit_code"] == 1
    assert results[0]["error_code"] == expected
    assert results[0]["attachment_elapsed_ms"] >= 0 and results[0]["next_steps"]
    assert "/private" not in json.dumps(results)
    assert results[0]["submission_state"] == "not_attempted" and results[0]["retry_safe"] is True
    browser_env.connect.assert_called_once()
    browser_env.runtime.__exit__.assert_called_once()


def test_disconnect_never_reconnects(browser_env, monkeypatch, capsys):
    browser_env.browser.is_connected.side_effect = [True, False, False, False]
    code, results = stream(monkeypatch, capsys, [["status"], ["status"]])
    assert code == 1 and results[-1]["error_code"] == "chrome_connection_lost"
    assert len(results) <= 2
    browser_env.connect.assert_called_once()
    browser_env.browser.close.assert_called_once()


@pytest.mark.parametrize("line", [None, {}, "status", [], [1], ["session"], ["doctor"],
    ["mcp", "begin"], ["--site", "https://other.atlassian.net", "status"],
    ["status", "--account", "other@example.com"], ["status", "--help"], ["chat"],
    ["chat", "--help"], ["ask", "--prompt-file", "-"], ["ask", "--prompt-file=-"]])
def test_invalid_stream_input_is_recoverable(browser_env, monkeypatch, capsys, line):
    code, results = stream(monkeypatch, capsys, [line, ["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 1, 0]
    assert results[1]["submission_state"] == "not_attempted" and results[1]["retry_safe"] is True
    browser_env.connect.assert_called_once()
    browser_env.target.submit.click.assert_not_called()


def test_malformed_json_does_not_break_framing(browser_env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{broken\n["status"]\n'))
    assert rovo_cli.run([*FLAGS, "session"]) == 0
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["exit_code"] for r in results] == [0, 1, 0]


def test_successful_ask_continues_despite_retry_unsafe(browser_env, monkeypatch, capsys, tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)], ["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 0, 0]
    assert results[1]["answer"] == "Synthetic answer" and results[1]["retry_safe"] is False
    browser_env.target.submit.click.assert_called_once()
    browser_env.connect.assert_called_once()


def test_preparation_error_preserves_connection(browser_env, monkeypatch, capsys, tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    browser_env.target.textbox.evaluate.return_value = "User draft"
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)], ["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 1, 0]
    browser_env.target.new_chat.click.assert_not_called()
    browser_env.target.submit.click.assert_not_called()
    browser_env.connect.assert_called_once()


@pytest.mark.parametrize("failure", [Error("Synthetic click failure"), KeyboardInterrupt()])
def test_uncertain_send_is_terminal_and_record_survives(browser_env, monkeypatch, capsys, tmp_path, failure):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    browser_env.target.submit.click.side_effect = failure
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)], ["status"]])
    assert code in (1, 3) and len(results) == 2
    assert results[-1]["submission_state"] == "attempted_unknown" and results[-1]["retry_safe"] is False
    assert read_request(state_dir(tmp_path, ORIGIN, "pilot"))["submission_state"] == "attempted_unknown"
    browser_env.target.submit.click.assert_called_once()
    browser_env.browser.close.assert_called_once()
    assert not list(tmp_path.rglob("control.lock"))


@pytest.mark.parametrize("failure", [None, Error("Synthetic cleanup failure")])
def test_cleanup_never_masks_original_result(browser_env, monkeypatch, capsys, failure):
    browser_env.browser.close.side_effect = failure
    code, results = stream(monkeypatch, capsys, [["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 0]
    browser_env.browser.close.assert_called_once()
    browser_env.runtime.__exit__.assert_called_once()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signals_detach_once_and_restore_handler(browser_env, monkeypatch, capsys, sig):
    previous = signal.getsignal(sig)

    class Input:
        def readline(self):
            signal.raise_signal(sig)

    monkeypatch.setattr(sys, "stdin", Input())
    assert rovo_cli.run([*FLAGS, "session"]) == 3
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert results[-1]["execution_status"] == "interrupted" and results[-1]["exit_code"] == 3
    browser_env.browser.close.assert_called_once()
    assert signal.getsignal(sig) == previous


def test_dry_run_validates_without_attachment_or_input(browser_env, monkeypatch, capsys):
    class Input:
        def readline(self):
            pytest.fail("Dry run must not read commands")

    monkeypatch.setattr(sys, "stdin", Input())
    assert rovo_cli.run([*FLAGS, "--dry-run", "session"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    browser_env.connect.assert_not_called()


def test_invalid_startup_still_uses_stream_schema(browser_env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('["status"]\n'))
    code = rovo_cli.run(["--site", "https://evil.test", "--session", "pilot", "--account", ACCOUNT, "session"])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["exit_code"] == 1 and result["submission_state"] == "not_attempted"
    browser_env.connect.assert_not_called()


def test_unexpected_stream_failure_is_terminal_json_and_detaches(browser_env, monkeypatch, capsys):
    class Input:
        def readline(self):
            raise RuntimeError("Unexpected private failure")

    monkeypatch.setattr(sys, "stdin", Input())
    assert rovo_cli.run([*FLAGS, "session"]) == 1
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert results[-1]["exit_code"] == 1 and results[-1]["retry_safe"] is False
    assert "private" not in results[-1]["message"]
    browser_env.browser.close.assert_called_once()


def test_delivery_checks_repeat_between_commands(browser_env, monkeypatch, capsys, tmp_path):
    class Input:
        reads = 0

        def readline(self):
            self.reads += 1
            assert self.reads == 1, "Blocked delivery must terminate the stream"
            directory = state_dir(tmp_path, ORIGIN, "other")
            with site_lock(directory):
                save_request(directory, {"submission_state": "attempted_unknown", "execution_status": "waiting"})
            return '["status"]\n'

    monkeypatch.setattr(sys, "stdin", Input())
    assert rovo_cli.run([*FLAGS, "session"]) == 4
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["exit_code"] for r in results] == [0, 4]
    browser_env.connect.assert_called_once()
    browser_env.browser.close.assert_called_once()


def test_mini_modal_stream_never_sends_or_lists(browser_env, monkeypatch, capsys, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1", layout=MINI_PANEL)
    browser_env.browser.contexts[0].pages = [target.page]
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)],
        ["chat", "list"], ["chat", "export", "--chat", "12345678-1234-4234-8234-123456789abc"], ["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 1, 1, 1, 0]
    assert all(r["error_code"] == "rovo_layout_unverified" for r in results[1:4])
    target.textbox.fill.assert_not_called()
    target.submit.click.assert_not_called()
    browser_env.connect.assert_called_once()


def test_timeout_ends_stream_without_resubmission(browser_env, monkeypatch, capsys, tmp_path):
    clock = SimpleNamespace(now=0)
    monkeypatch.setattr(rovo_backend.time, "monotonic", lambda: clock.now)
    browser_env.target.page.wait_for_timeout.side_effect = lambda _: setattr(clock, "now", clock.now + 2)
    browser_env.target.status.inner_text.side_effect = None
    browser_env.target.status.inner_text.return_value = "Rovo is thinking"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text(PROMPT)
    code, results = stream(monkeypatch, capsys, [["ask", "--timeout", "1", "--prompt-file", str(prompt)], ["status"]])
    assert code == 3 and len(results) == 2 and results[-1]["execution_status"] == "timeout"
    assert read_request(state_dir(tmp_path, ORIGIN, "pilot"))["execution_status"] == "timeout"
    browser_env.target.submit.click.assert_called_once()
    browser_env.browser.close.assert_called_once()


@pytest.mark.parametrize("ending", ["exit", EOFError(), KeyboardInterrupt()])
def test_human_repl_also_reuses_connection(browser_env, monkeypatch, capsys, ending):
    from cli_anything.rovo.utils import repl_skin

    skin = MagicMock()
    command = " ".join([*FLAGS, "status"])
    skin.get_input.side_effect = [command, command, ending]
    monkeypatch.setattr(repl_skin, "ReplSkin", lambda *args, **kwargs: skin)
    assert rovo_cli.repl() == (3 if isinstance(ending, KeyboardInterrupt) else 0)
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(results) == 2 and all(r["execution_status"] == "completed" for r in results)
    browser_env.connect.assert_called_once()
    browser_env.browser.close.assert_called_once()


def test_failed_owner_cannot_attach_again(browser_env):
    browser_env.connect.side_effect = Error("Synthetic attach failure")
    with rovo_backend.BrowserConnection() as connection:
        for _ in range(2):
            result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
            assert code == 1 and result["error_code"] == "chrome_connection_failed"
    browser_env.connect.assert_called_once()


def test_runtime_cleanup_error_preserves_completed_result(browser_env, monkeypatch, capsys):
    browser_env.runtime.__exit__.side_effect = Error("Synthetic runtime cleanup failure")
    code, results = stream(monkeypatch, capsys, [])
    assert code == 0 and results[0]["exit_code"] == 0
    browser_env.browser.close.assert_called_once()
    browser_env.runtime.__exit__.assert_called_once()


def test_repl_cannot_nest_another_session(browser_env, monkeypatch, capsys):
    from cli_anything.rovo.utils import repl_skin

    skin = MagicMock()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    skin.get_input.side_effect = [" ".join([*FLAGS, "status"]), " ".join(FLAGS), "exit"]
    monkeypatch.setattr(repl_skin, "ReplSkin", lambda *args, **kwargs: skin)
    rovo_cli.repl()
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(results) == 2 and results[-1]["execution_status"] == "error"
    browser_env.connect.assert_called_once()
    browser_env.browser.close.assert_called_once()
