"""Durable guard for agent-mediated Playwright MCP submissions; never controls a browser."""
import hashlib
from uuid import uuid4

from .state import (
    blocking_request, bounded_answer, completed_turn, read_request, save_request,
    site_lock, state_dir, unresolved, validate_target,
)


def begin_handoff(home, origin, session, account, prompt, before):
    origin = validate_target(origin, session, account)
    prompt = prompt.strip()
    if not 1 <= len(prompt) <= 120000 or type(before) is not int or before < 0:
        raise ValueError("Provide a nonempty prompt up to 120000 characters and a nonnegative response baseline.")
    directory = state_dir(home, origin, session)
    with site_lock(directory):
        if blocking_request(directory):
            raise ValueError("Prior delivery remains unresolved; do not submit through either transport.")
        record = {"request_id": str(uuid4()), "site": origin, "session": session, "account": account,
                  "transport": "playwright_mcp", "submission_state": "attempted_unknown",
                  "execution_status": "waiting", "before": before,
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        marker = directory.parent / ".mcp"
        marker.mkdir(mode=0o700, exist_ok=True)
        # Reserve before the external click: a crash must block rather than duplicate delivery.
        save_request(marker, record)
        return record


def finish_handoff(home, origin, session, account, evidence):
    origin = validate_target(origin, session, account)
    directory = state_dir(home, origin, session)
    with site_lock(directory):
        marker = directory.parent / ".mcp"
        record = read_request(marker)
        if (not unresolved(record) or not isinstance(evidence, dict)
                or any(record.get(k) != v for k, v in {"site": origin, "session": session, "account": account}.items())
                or any(evidence.get(k) != record[k] for k in ("request_id", "site", "account"))):
            raise ValueError("Completion does not match the pending MCP request; leave it blocked.")
        for key, expected in {"started": bool, "generating": bool, "count": int,
                              "status": str, "user_text": str, "answer": str}.items():
            if type(evidence.get(key)) is not expected:
                raise ValueError("Invalid completion evidence; leave the request blocked.")
        if len(evidence["user_text"]) > 120000 or len(evidence["answer"]) > 1000000:
            raise ValueError("Completion evidence exceeds local limits.")
        matches = hashlib.sha256(evidence["user_text"].strip().encode()).hexdigest() == record["prompt_sha256"]
        if not completed_turn(started=evidence["started"], count=evidence["count"],
                              status=evidence["status"], generating=evidence["generating"],
                              answer=evidence["answer"], before=record["before"], prompt_matches=matches):
            raise ValueError("No correlated completed response; leave the request blocked.")
        record.update(execution_status="completed", submission_state="observed_submitted")
        save_request(marker, record)
        return record | bounded_answer(evidence["answer"]) | {
            "schema_version": 1, "completion_evidence": "agent_observed", "retry_safe": False,
            "retrieval_assessment": "unverified", "context_percent": None,
        }
