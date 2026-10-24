"""Private local attempt state; remote delivery is never inferred from a timeout."""
import json
import os
import re
import tempfile
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit


def validate_target(site, session, account):
    if not site or any(c.isspace() for c in site):
        raise ValueError("Provide a valid HTTPS Atlassian site.")
    url = urlsplit(site)
    if (url.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.atlassian\.net", url.hostname or "")
            or url.username or url.password or url.port not in (None, 443) or url.query or url.fragment):
        raise ValueError("Use an HTTPS SITE.atlassian.net URL without credentials, query, fragment or custom port.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session or ""):
        raise ValueError("Provide a session containing only letters, digits, underscore or hyphen.")
    if not account or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account):
        raise ValueError("Provide the expected Atlassian account email.")
    return "https://" + url.hostname


def state_dir(home, origin, session):
    # Keep the original state directory so renaming cannot bypass uncertain-delivery guards.
    return Path(home) / ".cli-anything-rovo" / urlsplit(origin).hostname / session


def read_request(directory):
    path = directory / "request.json"
    return json.loads(path.read_text()) if path.exists() else None


def unresolved(record):
    return bool(record and record["submission_state"] != "not_attempted"
                and record["execution_status"] != "completed")


def next_action(payload, code):
    """The one agent decision for a direct result: ask, new_or_inspect, mcp_fallback, fix_or_report, reconcile or stop."""
    status, error = payload.get("execution_status"), payload.get("error_code")
    attempted = payload.get("submission_state") not in (None, "not_attempted")
    if code == 4 and payload.get("reconcilable") is True:
        return "reconcile"
    if code == 4 or status == "blocked" or (attempted and status != "completed"):
        return "stop"
    if status == "completed":
        # Status reports a prior unresolved request as retry_safe False; a completed ask is never retry-safe.
        if payload.get("readiness") == "authenticated_ui_read_only" or (
                "readiness" in payload and payload.get("retry_safe") is not True):
            return "stop"
        return "new_or_inspect" if payload.get("continuity_status") == "unavailable" else "ask"
    safe = payload.get("retry_safe") is True and not attempted
    if error == "chrome_debugging_unavailable" and safe:
        return "mcp_fallback"
    if error in ("continuity_unbound", "conversation_changed"):
        return "new_or_inspect"
    if error or status == "authentication_required":
        return "stop"
    # Browser-side failures (layout, timeouts) are not the agent's input to fix.
    return "fix_or_report" if code == 1 and safe and "browser_mode" not in payload else "stop"


def blocking_request(directory):
    """Uncertain delivery blocks every session and both transports on this site."""
    for path in sorted(directory.parent.glob("*/request.json")):
        record = read_request(path.parent)
        if unresolved(record):
            return record
    return None


@contextmanager
def site_lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive site lock covers distinct named sessions targeting the same tab.
    path = directory.parent / "control.lock"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
        path.unlink()


def save_request(directory, record):
    # Caller owns site_lock. Atomic replacement preserves the last valid attempt on crash.
    fd, name = tempfile.mkstemp(prefix=".request-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / "request.json")
        parent = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def plain(text):
    """Prompt text as the composer, the rendered turn and Rovo's data all show it: non-blank lines,
    spaces collapsed. Rovo's editor turns each line into a paragraph, adding blank lines between."""
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def completed_turn(*, started, count, status, generating, answer, before=0, prompt_matches=True, new_id=False):
    """new_id: the last turn carries a message ID the chat did not have before submit. A virtualized
    panel can drop an old turn as the new one renders, so the count alone cannot prove a new turn."""
    return started and (count > before or new_id is True) and prompt_matches and status.strip() == "Response complete." and generating is False and bool(answer.strip())


def provable(record):
    """An uncertain attempt that names its chat, prompt hash and the turns the chat had before it."""
    return bool(unresolved(record) and record.get("chat_id") and record.get("prompt_sha256")
                and type(record.get("turns_before")) is int)


def delivered(messages, prompt_sha256, before):
    """(reply, None) when the prompt appears exactly once as a human turn after the first `before`
    turns and Rovo answered it; otherwise (None, reason)."""
    humans = [i for i, message in enumerate(messages) if message["role"] == "HUMAN"]
    sent = [i for i in humans[before:] if sha256(plain(messages[i]["text"]).encode()).hexdigest() == prompt_sha256]
    if not sent:
        return None, "prompt_missing"
    if len(sent) > 1:
        return None, "prompt_duplicated"
    reply = messages[sent[0] + 1] if sent[0] + 1 < len(messages) else None
    if not reply or reply["role"] != "ASSISTANT" or not reply["text"].strip():
        return None, "answer_missing"
    return reply, None


def bounded_answer(answer, limit=12000):
    return {"answer": answer[:limit], "truncated": len(answer) > limit}


def load_images(paths):
    """Local PNG policy; retain validated bytes so later file replacement cannot change uploads."""
    if len(paths) > 4:
        raise ValueError("At most four images per request (local policy).")
    images = []
    for item in paths:
        path = Path(item)
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError("Each image must be a readable regular PNG file.")
        if path.name in {image["name"] for image in images}:
            raise ValueError("Image filenames must be unique within the request.")
        with path.open("rb") as stream:
            data = stream.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Images require a PNG signature and size at most 5 MiB (local policy).")
        images.append({"name": path.name, "mimeType": "image/png", "buffer": data})
    return images
