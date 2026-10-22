"""Installed-command checks only; real Rovo gate documented separately in TEST.md."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _resolve_cli(name):
    path = shutil.which(name)
    if path:
        return [path]
    if os.getenv("CLI_ANYTHING_FORCE_INSTALLED") == "1":
        raise RuntimeError("Install rovo-relay-cli and put it on PATH first.")
    return [sys.executable, "-m", "cli_anything.rovo"]


class TestCLISubprocess:
    def run(self, *args, command="rovo-relay-cli"):
        return subprocess.run(_resolve_cli(command) + list(args), text=True, capture_output=True, timeout=10)

    def test_doctor_and_packaged_skill(self):
        output = self.run("--json", "doctor")
        assert output.returncode == 0, output.stderr
        result = json.loads(output.stdout)
        assert result["authenticated"] == "not_checked"
        assert Path(result["skill_path"]).is_file()
        assert "\nname: ask-rovo\n" in Path(result["skill_path"]).read_text()
        assert Path(result["skill_path"]).with_name("MCP_FALLBACK.md").is_file()
        assert result["mcp_handoff"] == "agent_tools_with_local_guard"

    def test_invalid_argument_json_no_submission(self):
        output = self.run("--json", "--dry-run", "--site", "https://evil.test", "--session", "probe", "--account", "a@example.com", "status")
        assert output.returncode == 1
        result = json.loads(output.stdout)
        assert result["schema_version"] == 1 and result["submission_state"] == "not_attempted"

    def test_dry_run_does_not_contact_browser(self, tmp_path):
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("A harmless test prompt")
        output = self.run("--json", "--dry-run", "--site", "https://x.atlassian.net", "--session", "probe", "--account", "a@example.com", "ask", "--prompt-file", str(prompt))
        assert output.returncode == 0, output.stderr
        assert json.loads(output.stdout)["submission_state"] == "not_attempted"

    def test_noninteractive_requires_command(self):
        output = self.run("--json")
        assert output.returncode == 1
        assert json.loads(output.stdout)["retry_safe"] is True

    def test_session_help_and_dry_run(self):
        output = self.run("session", "--help")
        assert output.returncode == 0 and "JSON" in output.stdout
        output = self.run("--site", "https://x.atlassian.net", "--session", "probe",
                          "--account", "a@example.com", "--dry-run", "session")
        assert output.returncode == 0, output.stderr
        result = json.loads(output.stdout)
        assert result["dry_run"] is True and result["exit_code"] == 0
        assert "session" in json.loads(self.run("doctor").stdout)["implemented"]

    def test_explicit_chrome_port_validation_and_dry_run(self):
        args = ["--site", "https://example.atlassian.net", "--session", "probe", "--account", "user@example.com"]
        output = self.run(*args, "--chrome-port", "9222", "--dry-run", "session")
        assert output.returncode == 0, output.stderr
        assert json.loads(output.stdout)["dry_run"] is True
        output = self.run(*args, "--chrome-port", "65536", "--dry-run", "session")
        assert output.returncode == 1 and json.loads(output.stdout)["submission_state"] == "not_attempted"

    def test_image_dry_run_and_rejection(self, tmp_path):
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("Describe the image")
        image = tmp_path / "image.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        args = ["--json", "--dry-run", "--site", "https://x.atlassian.net", "--session", "probe", "--account", "a@example.com", "ask", "--prompt-file", str(prompt), "--image", str(image)]
        output = self.run(*args)
        assert output.returncode == 0, output.stderr
        data = json.loads(output.stdout)
        assert data["image_count"] == 1 and data["submission_state"] == "not_attempted"
        assert str(image) not in output.stdout and "fixture" not in output.stdout
        image.write_bytes(b"invalid")
        output = self.run(*args)
        assert output.returncode == 1
        assert json.loads(output.stdout)["submission_state"] == "not_attempted"

    def test_source_choice_and_dry_run(self, tmp_path):
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("Read a repository file")
        args = ["--json", "--dry-run", "--site", "https://x.atlassian.net", "--session", "probe", "--account", "a@example.com", "ask", "--prompt-file", str(prompt), "--github-source"]
        for choice in ("on", "off"):
            output = self.run(*args, choice)
            assert output.returncode == 0
            assert json.loads(output.stdout)["github_source_requested"] == choice
        output = self.run(*args, "enable-admin")
        assert output.returncode == 1 and json.loads(output.stdout)["submission_state"] == "not_attempted"

    def test_chat_id_validation_and_export_dry_run(self):
        args = ["--json", "--dry-run", "--site", "https://x.atlassian.net", "--session", "probe", "--account", "a@example.com", "chat", "export", "--chat"]
        output = self.run(*args, "not-a-uuid")
        assert output.returncode == 1
        output = self.run(*args, "12345678-1234-4234-8234-123456789abc")
        assert output.returncode == 0
        assert json.loads(output.stdout)["chat_id"] == "12345678-1234-4234-8234-123456789abc"

    def test_installed_mcp_handoff_shares_pending_delivery_with_legacy_alias(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        prompt = tmp_path / "prompt.txt"
        prompt.write_text("A guarded MCP question")
        args = ["--json", "--site", "https://x.atlassian.net", "--session", "probe", "--account", "a@example.com"]
        begin = ["mcp", "begin", "--prompt-file", str(prompt), "--before-count", "0"]
        output = self.run(*args, "--dry-run", *begin)
        assert output.returncode == 0, output.stdout
        assert not list(tmp_path.rglob("request.json"))
        output = self.run(*args, *begin)
        assert output.returncode == 0, output.stdout
        record = json.loads(output.stdout)
        repeated = self.run(*args, *begin, command="rovo-relay")
        assert repeated.returncode == 4
        assert json.loads(repeated.stdout)["retry_safe"] is False
        proof = tmp_path / "completion.json"
        proof.write_text(json.dumps(dict(request_id=record["request_id"], site="https://x.atlassian.net", account="a@example.com",
                                        started=True, count=1, status="Response complete.", generating=False,
                                        user_text="A guarded MCP question", answer="A guarded MCP answer")))
        output = self.run(*args, "mcp", "finish", "--evidence-file", str(proof))
        assert output.returncode == 0, output.stdout
        assert json.loads(output.stdout)["answer"] == "A guarded MCP answer"
