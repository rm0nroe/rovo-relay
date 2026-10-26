"""The broker holds one approved Chrome connection for later one-shot commands; no Chrome or Rovo here."""
import json
import os
import shutil
import socket
import stat
import tempfile
import threading
import time
from pathlib import Path

import pytest

from cli_anything.rovo import rovo_cli

SITE = ["--site", "https://example.atlassian.net", "--session", "probe", "--account", "user@example.com"]


class FakeConnection:
    made = []

    def __init__(self, chrome_port=None, approve_chrome_prompt=False):
        self.chrome_port, self.approve_chrome_prompt = chrome_port, approve_chrome_prompt
        self.failed, self.gets = False, 0
        FakeConnection.made.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.failed = True

    def get(self):
        self.gets += 1


@pytest.fixture
def fake(monkeypatch):
    # Unix socket paths are limited to about 104 bytes, longer than pytest's tmp_path on macOS.
    home = Path(tempfile.mkdtemp(prefix="rovo", dir="/tmp"))
    monkeypatch.setattr(rovo_cli, "broker_path", lambda: home / "broker.sock")
    monkeypatch.setattr(rovo_cli, "BrowserConnection", FakeConnection)
    FakeConnection.made = []
    calls = []

    def operate(origin, session, account, prompt=None, connection=None, **kwargs):
        calls.append((session, prompt, connection))
        if session == "stop":
            connection.failed = True
        code = 4 if session == "blocked" else 0
        return {"schema_version": 1, "execution_status": "blocked" if code else "completed", "answer": prompt,
                "submission_state": "attempted_unknown" if code else "not_attempted", "retry_safe": not code}, code

    monkeypatch.setattr(rovo_cli, "operate", operate)
    yield home, calls
    shutil.rmtree(home, ignore_errors=True)


def serve(home, clients, idle="1"):
    """Run the broker here (it installs signal handlers) while `clients` run in a thread."""
    results = []

    def run_clients():
        deadline = time.monotonic() + 5
        while not (home / "broker.sock").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        for client in clients:
            results.append(client())

    thread = threading.Thread(target=run_clients)
    thread.start()
    code = rovo_cli.run(["--chrome-port", "9222", "broker", "--idle-minutes", idle])
    thread.join(5)
    return code, results


def one_shot(*args):
    return lambda: rovo_cli.run([*SITE, *args])


def stop():
    return rovo_cli.run(["--site", "https://example.atlassian.net", "--session", "stop", "--account", "user@example.com", "status"])


def test_one_approval_serves_every_one_shot_command(fake, capsys, tmp_path, monkeypatch):
    home, calls = fake
    (tmp_path / "prompt.txt").write_text("Synthetic question")
    monkeypatch.chdir(tmp_path)
    code, results = serve(home, [one_shot("status"), one_shot("ask", "--prompt-file", "prompt.txt"), stop])
    assert results == [0, 0, 0] and code == 0
    # One connection, attached once at startup, shared by every forwarded command.
    assert len(FakeConnection.made) == 1 and FakeConnection.made[0].gets == 1
    assert {id(connection) for _, _, connection in calls} == {id(FakeConnection.made[0])}
    # The relative prompt file was read from the client's directory.
    assert calls[1][1] == "Synthetic question"
    # Broker and client lines interleave on this shared stdout.
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["execution_status"] == "ready" and lines[-1]["reason"] == "connection_lost"
    assert sum(line.get("answer") == "Synthetic question" for line in lines) == 2  # broker log + client
    assert not (home / "broker.sock").exists()


def test_blocked_result_keeps_the_broker_for_the_next_command(fake):
    home, _ = fake
    blocked = lambda: rovo_cli.run(["--site", "https://example.atlassian.net", "--session", "blocked", "--account", "user@example.com", "status"])
    code, results = serve(home, [blocked, one_shot("status"), stop])
    assert results == [4, 0, 0], results


def test_socket_is_owner_only(fake):
    home, _ = fake
    modes = []
    serve(home, [lambda: modes.append(stat.S_IMODE(os.stat(home / "broker.sock").st_mode)), stop])
    assert modes == [0o600]


def test_idle_broker_exits_and_removes_its_socket(fake, capsys):
    home, _ = fake
    code, _ = serve(home, [], idle="0.005")
    assert code == 0 and json.loads(capsys.readouterr().out.splitlines()[-1])["reason"] == "idle"
    assert not (home / "broker.sock").exists()


def test_stale_socket_runs_the_command_directly(fake):
    home, calls = fake
    with socket.socket(socket.AF_UNIX) as stale:
        stale.bind(str(home / "broker.sock"))
    assert rovo_cli.run([*SITE, "status"]) == 0
    assert [(session, connection) for session, _, connection in calls] == [("probe", None)]


@pytest.mark.parametrize("args", [["--dry-run", "status"], ["status", "--help"], ["ask", "--prompt-file", "-"], ["doctor"], ["mcp", "begin", "--prompt-file", os.devnull]])
def test_commands_the_broker_cannot_serve_never_reach_it(fake, args):
    home, _ = fake
    contacted = []
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(home / "broker.sock"))
        server.listen(1)
        server.settimeout(0.3)

        def listen():
            try:
                contacted.append(server.accept())
            except TimeoutError:
                pass
        thread = threading.Thread(target=listen)
        thread.start()
        rovo_cli.run([*SITE, *args])
        thread.join(1)
    assert contacted == []


def test_broker_that_never_replies_is_uncertain_not_retried(fake, capsys):
    home, calls = fake
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(home / "broker.sock"))
        server.listen(1)
        threading.Thread(target=lambda: server.accept()[0].close()).start()
        code = rovo_cli.run([*SITE, "ask", "--prompt-file", os.devnull])
    result = json.loads(capsys.readouterr().out)
    assert code == 3 and result["submission_state"] == "attempted_unknown" and result["next"] == "stop", result
    assert calls == []  # never fell back to sending directly


def test_second_broker_refuses_while_one_is_live(fake, capsys):
    home, _ = fake
    code, results = serve(home, [lambda: rovo_cli.run(["--chrome-port", "9222", "broker"]), stop])
    assert results[0] == 1
    assert "already running" in capsys.readouterr().out


def test_request_without_a_result_does_not_stop_the_broker(fake):
    home, _ = fake

    def raw(argv):
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(home / "broker.sock"))
            client.sendall(json.dumps({"argv": argv, "cwd": "/"}).encode() + b"\n")
            return json.loads(client.makefile().readline())["code"]
    code, results = serve(home, [lambda: raw([*SITE, "status", "--help"]), one_shot("status"), stop])
    assert results == [1, 0, 0], results


def test_site_and_account_default_from_the_environment(monkeypatch, capsys):
    monkeypatch.setenv("ROVO_RELAY_SITE", "https://example.atlassian.net/jira")
    monkeypatch.setenv("ROVO_RELAY_ACCOUNT", "user@example.com")
    assert rovo_cli.run(["--dry-run", "--session", "probe", "status"]) == 0
    # Explicit flags win over the environment, in either option spelling.
    assert rovo_cli.run(["--dry-run", "--site=https://other.atlassian.net", "--session", "probe", "status"]) == 0
    assert [json.loads(line)["site"] for line in capsys.readouterr().out.splitlines()] == [
        "https://example.atlassian.net", "https://other.atlassian.net"]
    # Defaults are expanded before forwarding, so a broker serves the caller's values, not its own.
    assert rovo_cli.with_env_defaults(["status"]) == [
        "--site", "https://example.atlassian.net/jira", "--account", "user@example.com", "status"]
    monkeypatch.delenv("ROVO_RELAY_ACCOUNT")
    assert rovo_cli.run(["--dry-run", "--session", "probe", "status"]) == 1
