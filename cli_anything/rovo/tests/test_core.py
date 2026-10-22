import json

import pytest

from cli_anything.rovo.core.state import (
    bounded_answer, completed_turn, load_images, read_request, save_request, site_lock, state_dir, unresolved, validate_target,
)


@pytest.mark.parametrize("site", ["http://x.atlassian.net", "https://x.atlassian.net.evil.test",
    "https://u:secret@x.atlassian.net", "https://x.atlassian.net:9999", "https://x.atlassian.net/#secret",
    "https://x.atlassian.net/?token=secret", "https://x.atlassian.net\n"])
def test_reject_wrong_destination(site):
    with pytest.raises(ValueError):
        validate_target(site, "probe", "test@example.com")


def test_target_normalizes_origin_and_rejects_bad_identity():
    assert validate_target("https://x.atlassian.net/jira", "probe", "test@example.com") == "https://x.atlassian.net"
    for session, account in [("../escape", "test@example.com"), ("", "test@example.com"), ("ok", "")]:
        with pytest.raises(ValueError):
            validate_target("https://x.atlassian.net", session, account)


def test_site_lock_excludes_different_sessions_and_releases(tmp_path):
    one = state_dir(tmp_path, "https://x.atlassian.net", "one")
    two = state_dir(tmp_path, "https://x.atlassian.net", "two")
    with site_lock(one):
        with pytest.raises(FileExistsError):
            with site_lock(two):
                pytest.fail("Acquired a concurrent site lock")
    with site_lock(two):
        assert (two.parent / "control.lock").exists()
    assert not (two.parent / "control.lock").exists()


def test_request_survives_failure_and_unknown_delivery_blocks(tmp_path):
    directory = state_dir(tmp_path, "https://x.atlassian.net", "probe")
    record = {"request_id": "test", "submission_state": "attempted_unknown", "execution_status": "waiting"}
    with site_lock(directory):
        save_request(directory, record)
    loaded = read_request(directory)
    assert loaded == record and unresolved(loaded)
    assert "prompt" not in json.dumps(loaded)
    assert (directory / "request.json").stat().st_mode & 0o077 == 0
    assert not unresolved(record | {"execution_status": "completed"})
    assert not unresolved(None)


def test_terminal_status_without_observed_start_is_not_completion():
    good = dict(started=True, count=1, status="Response complete.", generating=False, answer="ok")
    assert completed_turn(**good)
    for change in [dict(started=False), dict(count=0), dict(status="Rovo is thinking"), dict(status="Message sent."), dict(generating=True), dict(answer=" "), dict(before=1), dict(prompt_matches=False)]:
        assert not completed_turn(**(good | change))


def test_output_cap_is_explicit():
    assert bounded_answer("abcdef", 3) == {"answer": "abc", "truncated": True}
    assert bounded_answer("abc", 3) == {"answer": "abc", "truncated": False}


def test_images_reject_wrong_format_count_size_and_duplicate_name(tmp_path):
    image = tmp_path / "test.png"
    image.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        load_images([image])
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024))
    with pytest.raises(ValueError):
        load_images([image])
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    with pytest.raises(ValueError):
        load_images([image, image])
    with pytest.raises(ValueError):
        load_images([image] * 5)
    with pytest.raises(ValueError):
        load_images([tmp_path])
    loaded = load_images([image])
    image.write_bytes(b"replaced")
    assert loaded[0]["buffer"] == b"\x89PNG\r\n\x1a\nfixture"
    assert loaded[0]["name"] == "test.png" and loaded[0]["mimeType"] == "image/png"


@pytest.mark.parametrize("prompt", [None, "Do not submit this prompt"])
def test_missing_chrome_endpoint_gives_safe_setup_steps(monkeypatch, tmp_path, prompt):
    from pathlib import Path
    from playwright.sync_api import BrowserType, Error
    from cli_anything.rovo.utils.rovo_backend import operate

    def missing_endpoint(self, *args, **kwargs):
        raise Error("Could not connect to chrome: DevToolsActivePort file not found at /private-fixture/profile/DevToolsActivePort.\nEnable remote debugging first.")

    monkeypatch.setattr(BrowserType, "connect_over_cdp", missing_endpoint)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result, code = operate("https://x.atlassian.net", "probe", "test@example.com", prompt=prompt)
    assert code == 1
    assert result["submission_state"] == "not_attempted" and result["retry_safe"] is True
    assert result["error_code"] == "chrome_debugging_unavailable"
    assert "chrome://inspect/#remote-debugging" in " ".join(result["next_steps"])
    assert "/private-fixture/" not in json.dumps(result)
    assert not list(tmp_path.rglob("request.json"))
    assert not list(tmp_path.rglob("control.lock"))
