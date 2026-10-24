"""Persistent foreground sessions, using only synthetic browser-boundary doubles."""
import io
import json
import signal
import sys
from itertools import chain, count, repeat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Browser, Error

from cli_anything.rovo import rovo_cli
from cli_anything.rovo.core.state import read_request, save_request, site_lock, state_dir
from cli_anything.rovo.utils import rovo_backend
from test_continuity import count_reads
from test_browser_tabs import ACCOUNT, MESSAGE_ID, MINI_PANEL, ORIGIN, PROMPT, owned_context, page_fixture

FLAGS = ["--site", ORIGIN, "--session", "pilot", "--account", ACCOUNT]


@pytest.fixture
def browser_env(monkeypatch, tmp_path):
    target = page_fixture(ORIGIN + "/browse/DEMO-1")
    browser = MagicMock(spec=Browser)
    browser.contexts = [owned_context([], target.page)]
    browser.is_connected.return_value = True
    runtime = MagicMock()
    connect = runtime.__enter__.return_value.chromium.connect_over_cdp
    connect.return_value = browser
    monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: runtime)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(rovo_backend, "time", SimpleNamespace(monotonic=count(step=0.1).__next__))
    return SimpleNamespace(target=target, browser=browser, runtime=runtime, connect=connect)


def stream(monkeypatch, capsys, lines, *flags):
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(line) + "\n" for line in lines)))
    code = rovo_cli.run([*FLAGS, *flags, "session"])
    output = capsys.readouterr()
    return code, [json.loads(line) for line in output.out.splitlines()]


def test_stream_reuses_connection_and_rechecks_account(browser_env, monkeypatch, capsys):
    env = browser_env
    identity = env.target.page.get_by_role("button", name=ACCOUNT, exact=True)
    from itertools import chain, repeat
    identity.is_visible.side_effect = chain([True, True], repeat(False))
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
    assert results[0]["version"] == rovo_cli.__version__ and "agent next action" in results[0]["implemented"]
    assert [r["next"] for r in results] == ["ask", "ask"] and "implemented" not in results[1]
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


def test_closed_owned_tab_is_replaced_without_reconnecting(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        first, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 0, first
        second = page_fixture(ORIGIN + "/jira/for-you", layout=MINI_PANEL)
        env.target.page.is_closed.return_value = True
        env.browser.contexts[0].new_page.return_value = second.page
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


def test_attachment_notice_precedes_connection_and_is_not_repeated(browser_env, monkeypatch, capsys):
    class Stderr(io.StringIO):
        flushed = False

        def flush(self):
            self.flushed = True
            super().flush()

    stderr = Stderr()
    monkeypatch.setattr(sys, "stderr", stderr)

    def connect(*args, **kwargs):
        assert stderr.flushed
        assert "20-second attachment timeout" in stderr.getvalue()
        assert "If Chrome asks" in stderr.getvalue()
        return browser_env.browser

    browser_env.connect.side_effect = connect
    code, results = stream(monkeypatch, capsys, [["status"], ["status"]])
    assert code == 0 and [r["exit_code"] for r in results] == [0, 0, 0]
    assert stderr.getvalue().count("Connecting to Chrome") == 1
    browser_env.connect.assert_called_once()
    browser_env.target.submit.click.assert_not_called()


@pytest.mark.parametrize("phase", ["runtime_startup", "browser_attachment"])
def test_connection_failure_reports_the_actual_phase(browser_env, monkeypatch, capsys, phase):
    operation = browser_env.runtime.__enter__ if phase == "runtime_startup" else browser_env.connect
    operation.side_effect = Error("Synthetic failure at /private/profile/secret")
    code, results = stream(monkeypatch, capsys, [["status"]])
    assert code == 1 and len(results) == 1
    result = results[0]
    assert result["attachment_phase"] == phase
    assert result["attachment_timeout_ms"] == 20000
    assert result["error_code"] == "chrome_connection_failed"
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    assert "/private" not in json.dumps(result)
    if phase == "runtime_startup":
        browser_env.connect.assert_not_called()
    else:
        browser_env.connect.assert_called_once()
    browser_env.target.submit.click.assert_not_called()


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
    browser_env.browser.contexts[0].new_page.return_value = target.page
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
    snapshot = browser_env.target.panel.evaluate.side_effect
    # Each in-page wait slice uses up fake time, as a real slice would.
    browser_env.target.panel.evaluate.side_effect = lambda script, arg=None: (
        setattr(clock, "now", clock.now + 2), snapshot(script, arg))[1]
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


def test_owned_tab_is_reused_when_other_rovo_tabs_appear(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)[1] == 0
        unrelated = page_fixture(ORIGIN + "/browse/DEMO-2", draft="User draft")
        env.browser.contexts[0].pages = [unrelated.page]
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)[1] == 0
        env.browser.contexts[0].new_page.assert_called_once()
        env.target.page.goto.assert_called_once()
        assert not unrelated.page.mock_calls
        env.target.page.reload.assert_not_called()


@pytest.mark.parametrize("contexts", [0, 2])
def test_ambiguous_or_missing_chrome_context_never_creates_page(browser_env, contexts):
    env = browser_env
    context = env.browser.contexts[0]
    env.browser.contexts = [context] * contexts
    result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT)
    assert code == 1 and "context" in result["message"], result
    context.new_page.assert_not_called()


def test_closed_tab_cannot_bypass_unresolved_delivery(browser_env, tmp_path):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)[1] == 0
        env.target.page.is_closed.return_value = True
        directory = state_dir(tmp_path, ORIGIN, "other")
        with site_lock(directory):
            save_request(directory, {"submission_state": "attempted_unknown", "execution_status": "waiting"})
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 4 and result["retry_safe"] is False
        env.browser.contexts[0].new_page.assert_called_once()


def test_navigated_owned_tab_is_not_replaced_or_reloaded(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)[1] == 0
        env.target.page.url = "https://other.atlassian.net/jira/for-you"
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 1 and "left the requested" in result["message"], result
        env.browser.contexts[0].new_page.assert_called_once()
        env.target.page.goto.assert_called_once()
        env.target.page.reload.assert_not_called()
    env.target.page.close.assert_not_called()


def test_navigation_timeout_can_finish_loading_without_another_navigation(browser_env):
    env = browser_env
    env.target.page.goto.side_effect = Error("Navigation timeout")
    with rovo_backend.BrowserConnection() as connection:
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 1 and result["readiness_phase"] == "page_navigation", result
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 0, result
        env.target.page.goto.assert_called_once()
        env.target.page.reload.assert_not_called()
        env.browser.contexts[0].new_page.assert_called_once()


def test_tab_closed_while_stdin_waits_drains_cached_events_before_selection(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)[1] == 0
        replacement = page_fixture(ORIGIN + "/jira/for-you", panel_open=False)
        env.browser.contexts[0].new_page.return_value = replacement.page

        def deliver_close_event(delay):
            assert delay == 0
            env.target.page.is_closed.return_value = True
            raise Error("Target page, context or browser has been closed")

        env.target.page.wait_for_timeout.side_effect = deliver_close_event
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection)
        assert code == 0 and result["readiness_phase"] == "ready", result
        assert env.browser.contexts[0].new_page.call_count == 2
        replacement.launcher.click.assert_called_once()
        env.target.submit.click.assert_not_called()
        replacement.submit.click.assert_not_called()
    env.connect.assert_called_once()


def test_two_asks_auto_continue_in_one_foreground_connection(browser_env, monkeypatch, capsys, tmp_path):
    prompt = tmp_path / "question.txt"
    prompt.write_text(PROMPT)
    browser_env.target.status.inner_text.side_effect = ["Rovo is thinking", "Response complete."] * 2
    calls = count_reads(monkeypatch)
    code, results = stream(monkeypatch, capsys, [["ask", "--prompt-file", str(prompt)]] * 2)
    assert code == 0 and [r["exit_code"] for r in results] == [0, 0, 0], results
    first, second = results[1:]
    assert first["chat_id"] == second["chat_id"]
    assert second["conversation_mode"] == "continued" and second["turn_count"] == 2
    assert second["chat_selection"] == "warm_tab" and "chat_selection" not in first
    browser_env.connect.assert_called_once()
    browser_env.target.new_chat.click.assert_called_once()
    assert browser_env.target.submit.click.call_count == 2
    # New-chat capture binds from the send request; the follow-up reuses the verified open chat.
    browser_env.target.row.click.assert_not_called()
    # New chat: idle before and after the click, signature at capture. Warm follow-up: one idle
    # check; signature in warm_tab, after fill and at capture. Exit cleanup: one of each.
    assert calls == {"require_idle": 2 + 1 + 1, "turn_signature": 1 + 3 + 1}
    browser_env.target.page.close.assert_called_once()


def warm_ask(connection):
    return rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, connection=connection)


def test_warm_tab_survives_show_more_during_preparation(browser_env):
    env = browser_env
    env.target.status.inner_text.side_effect = ["Rovo is thinking", "Response complete."] * 2
    with rovo_backend.BrowserConnection() as connection:
        assert warm_ask(connection)[1] == 0
        env.target.identity.is_visible.side_effect = chain([False], repeat(True))
        env.target.more.is_visible.return_value = True
        result, code = warm_ask(connection)
    assert code == 0 and result["chat_selection"] == "warm_tab", result
    env.target.more.click.assert_called_once()
    env.target.row.click.assert_not_called()


def consume_with_failed_ask(env, connection, directory):
    env.target.textbox.evaluate.return_value = "Leftover draft"
    assert warm_ask(connection)[1] == 1
    env.target.textbox.evaluate.return_value = ""


def rewrite_request_id(env, connection, directory):
    with site_lock(directory):
        save_request(directory, read_request(directory) | {"request_id": "another-process"})


def consume_with_chat_list(env, connection, directory):
    env.target.rows.count.return_value = 1
    assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, action="chat_list", connection=connection)[1] == 0


FALLBACKS = {
    "panel_reopened": lambda env, *_: setattr(env.target.panel.is_visible, "return_value", False),
    "status_between": lambda env, connection, _: rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, connection=connection),
    "chat_list_between": consume_with_chat_list,
    "failed_ask_between": consume_with_failed_ask,
    "request_id_changed": rewrite_request_id,
    "search_visible": lambda env, *_: setattr(env.target.search.is_visible, "return_value", True),
    # Another chat whose last turn is identical: only the server message ID differs.
    "message_id_changed": lambda env, *_: setattr(env.target.message.get_attribute, "return_value", MESSAGE_ID.format(99)),
}
CHANGED = {
    "zero_groups": lambda env: setattr(env.target.groups.count, "return_value", 0),
    "count_changed": lambda env: setattr(env.target.groups.count, "return_value", 2),
    "text_changed": lambda env: setattr(env.target.user.inner_text, "return_value", "Another task"),
}


@pytest.mark.parametrize("case", FALLBACKS)
def test_unproven_warm_tab_falls_back_to_picker(browser_env, tmp_path, case):
    env = browser_env
    env.target.status.inner_text.side_effect = ["Rovo is thinking", "Response complete."] * 2
    with rovo_backend.BrowserConnection() as connection:
        assert warm_ask(connection)[1] == 0
        FALLBACKS[case](env, connection, state_dir(tmp_path, ORIGIN, "pilot"))
        result, code = warm_ask(connection)
    assert code == 0 and result["chat_selection"] == "picker" and result["turn_count"] == 2, result
    env.target.row.click.assert_called_once()
    assert env.target.submit.click.call_count == 2


@pytest.mark.parametrize("case", CHANGED)
def test_changed_open_chat_uses_picker_and_stops(browser_env, case):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert warm_ask(connection)[1] == 0
        CHANGED[case](env)
        result, code = warm_ask(connection)
    assert code == 1 and result["error_code"] == "conversation_changed", result
    env.target.row.click.assert_called_once()
    env.target.submit.click.assert_called_once()


def test_replaced_tab_uses_picker_even_with_matching_message(browser_env):
    env = browser_env
    with rovo_backend.BrowserConnection() as connection:
        assert warm_ask(connection)[1] == 0
        replacement = page_fixture(ORIGIN + "/jira/for-you")
        replacement.responses.count.return_value = replacement.groups.count.return_value = 1
        replacement.message.get_attribute.return_value = env.target.message.get_attribute.return_value
        env.browser.contexts[0].new_page.return_value = replacement.page
        env.target.page.is_closed.return_value = True
        result, code = warm_ask(connection)
    assert code == 0 and result["chat_selection"] == "picker", result
    replacement.row.click.assert_called_once()
    replacement.submit.click.assert_called_once()


def test_failed_operation_after_a_list_keeps_the_tab(browser_env):
    env = browser_env
    env.target.search.is_visible.return_value = True
    env.target.rows.evaluate_all.side_effect = None
    env.target.rows.evaluate_all.return_value = []
    env.target.rows.count.return_value = 0
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, action="chat_list", connection=connection)[1] == 0
        env.target.textbox.evaluate.return_value = "Leftover draft"
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, connection=connection)[1] == 1
    env.target.page.close.assert_not_called()


def test_ask_after_a_list_in_the_same_session_finds_the_composer(browser_env):
    env = browser_env
    search = env.target.search
    # The picker covers the composer while it is open.
    env.target.textbox.is_visible.side_effect = lambda: not search.is_visible.return_value
    all_chats = env.target.panel.get_by_role("button", name="View all conversations", exact=True)
    all_chats.click.side_effect = lambda **k: setattr(search.is_visible, "return_value", True)
    env.target.back.click.side_effect = lambda **k: setattr(search.is_visible, "return_value", False)
    env.target.rows.evaluate_all.side_effect = None
    env.target.rows.evaluate_all.return_value = []
    env.target.rows.count.return_value = 0
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, action="chat_list", connection=connection)[1] == 0
        env.target.back.click.assert_called_once()
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, connection=connection)
    assert code == 0, result.get("message")
    env.target.submit.click.assert_called_once()


def test_follow_up_in_the_same_tab_counts_its_own_turns_when_rovo_does_not_refetch(browser_env):
    from test_browser_tabs import CHAT, history, turns
    target = browser_env.target
    target.status.inner_text.side_effect = chain(*[["Rovo is thinking", "Response complete."]] * 2)
    target.responses.count.return_value = target.groups.count.return_value = 1
    texts = [text for n in range(9) for text in (f"Q{n}", f"A{n}")] + [PROMPT, "Synthetic answer"]
    fetched = []
    # Rovo fetches the chat once per tab; reopening it in the same tab serves its cache.
    target.row.click.side_effect = lambda **k: fetched or (fetched.append(1), history(target, turns(*texts), False, chat=CHAT))
    with rovo_backend.BrowserConnection() as connection:
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, chat_id=CHAT, connection=connection)
        assert code == 0 and result["turn_count"] == 11, result.get("message")
        target.search.is_visible.return_value = True  # The picker is open, so the open chat cannot prove itself.
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, connection=connection)
    assert code == 0 and result["continuity_status"] == "verified", result.get("message")
    assert result["chat_selection"] == "picker" and result["turn_count"] == 12


def test_a_new_chat_seeds_the_tab_record_with_its_first_turn(browser_env):
    from test_browser_tabs import CHAT
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, new=True, connection=connection)[1] == 0
        assert rovo_backend.server_turns(connection.history[browser_env.target.page], CHAT) == 1


def test_long_chat_follow_up_reuses_the_open_tab_and_exit_closes_it(browser_env):
    from test_browser_tabs import CHAT, history, turns
    target = browser_env.target
    target.status.inner_text.side_effect = chain(*[["Rovo is thinking", "Response complete."]] * 2)
    target.responses.count.return_value = target.groups.count.return_value = 1
    texts = [text for n in range(9) for text in (f"Q{n}", f"A{n}")] + [PROMPT, "Synthetic answer"]
    target.row.click.side_effect = lambda **k: history(target, turns(*texts), False, chat=CHAT)
    with rovo_backend.BrowserConnection() as connection:
        assert rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, chat_id=CHAT, connection=connection)[1] == 0
        # The virtualized page shows 2 of the chat's 11 turns.
        result, code = rovo_backend.operate(ORIGIN, "pilot", ACCOUNT, prompt=PROMPT, connection=connection)
        assert code == 0 and result["chat_selection"] == "warm_tab" and result["turn_count"] == 12, result.get("message")
    target.page.close.assert_called_once()
