import hashlib
from pathlib import Path

import pytest

from cli_anything.rovo.core.state import read_request, save_request, state_dir
from cli_anything.rovo.core.handoff import begin_handoff, finish_handoff

ORIGIN = "https://x.atlassian.net"
ACCOUNT = "test@example.com"
PROMPT = "Read the selected repository file"


def evidence(record, **changes):
    return dict(request_id=record["request_id"], site=ORIGIN, account=ACCOUNT,
                started=True, count=1, status="Response complete.", generating=False,
                user_text=PROMPT, answer="File summary", **changes)


def test_handoff_blocks_both_transports_and_other_sessions(monkeypatch, tmp_path):
    from cli_anything.rovo.utils import rovo_backend
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: pytest.fail("Must block before browser connection"))
    record = begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, PROMPT, 0)
    assert record["submission_state"] == "attempted_unknown"
    assert PROMPT not in str(read_request(state_dir(tmp_path, ORIGIN, ".mcp")))
    assert record["prompt_sha256"] == hashlib.sha256(PROMPT.encode()).hexdigest()
    with pytest.raises(ValueError, match="unresolved"):
        begin_handoff(tmp_path, ORIGIN, "two", ACCOUNT, PROMPT, 0)
    result, code = rovo_backend.operate(ORIGIN, "two", ACCOUNT, prompt=PROMPT)
    assert code == 4 and result["retry_safe"] is False
    assert result["request_id"] == record["request_id"]


def test_prior_cli_attempt_cannot_be_bypassed(monkeypatch, tmp_path):
    from cli_anything.rovo.utils import rovo_backend
    directory = state_dir(tmp_path, ORIGIN, "one")
    directory.mkdir(parents=True)
    save_request(directory, {"request_id": "prior", "submission_state": "attempted_unknown", "execution_status": "waiting"})
    with pytest.raises(ValueError, match="unresolved"):
        begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, PROMPT, 0)
    with pytest.raises(ValueError, match="unresolved"):
        begin_handoff(tmp_path, ORIGIN, "two", ACCOUNT, PROMPT, 0)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(rovo_backend, "sync_playwright", lambda: pytest.fail("Must block before status probes"))
    result, code = rovo_backend.operate(ORIGIN, "one", ACCOUNT)
    assert code == 4 and result["retry_safe"] is False


@pytest.mark.parametrize("change", [
    {"user_text": "Different prompt"}, {"count": 0}, {"started": False},
    {"generating": True}, {"status": "Rovo is thinking"}, {"answer": ""},
    {"account": "other@example.com"}, {"site": "https://other.atlassian.net"},
    {"request_id": "wrong"}, {"started": "false"}, {"count": True},
])
def test_incomplete_or_mismatched_evidence_stays_blocked(tmp_path, change):
    record = begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, PROMPT, 0)
    with pytest.raises(ValueError):
        finish_handoff(tmp_path, ORIGIN, "one", ACCOUNT, evidence(record) | change)
    with pytest.raises(ValueError, match="unresolved"):
        begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, PROMPT, 0)


def test_completion_requires_session_and_bounds_answer(tmp_path):
    record = begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, PROMPT, 0)
    proof = evidence(record) | {"answer": "x" * 12001}
    with pytest.raises(ValueError):
        finish_handoff(tmp_path, ORIGIN, "two", ACCOUNT, proof)
    result = finish_handoff(tmp_path, ORIGIN, "one", ACCOUNT, proof)
    assert result["execution_status"] == "completed"
    assert result["completion_evidence"] == "agent_observed"
    assert result["retrieval_assessment"] == "unverified"
    assert len(result["answer"]) == 12000 and result["truncated"] is True
    assert "answer" not in read_request(state_dir(tmp_path, ORIGIN, ".mcp"))
    next_record = begin_handoff(tmp_path, ORIGIN, "two", ACCOUNT, PROMPT, 1)
    assert next_record["request_id"] != record["request_id"]


def test_invalid_begin_never_creates_record(tmp_path):
    with pytest.raises(ValueError):
        begin_handoff(tmp_path, "https://evil.test", "one", ACCOUNT, PROMPT, 0)
    with pytest.raises(ValueError):
        begin_handoff(tmp_path, ORIGIN, "one", ACCOUNT, "", 0)
    assert not list(tmp_path.rglob("request.json"))
