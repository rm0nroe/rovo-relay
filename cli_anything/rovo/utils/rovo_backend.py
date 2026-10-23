"""Existing-Chrome Rovo adapter. No cookies, extension install or browser relaunch."""
import time
import re
import sys
from contextlib import nullcontext
from pathlib import Path
from uuid import UUID, uuid4
from hashlib import sha256
import json

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from cli_anything.rovo.core.state import (
    blocking_request, bounded_answer, completed_turn, read_request, save_request, site_lock, state_dir, unresolved,
)


class BrowserConnection:
    """Own one lazy CDP attachment; an attempted connection is never retried."""

    def __init__(self, chrome_port=None):
        self.chrome_port = chrome_port
        self.browser = None
        self.runtime = None
        self.attempted = False
        self.failed = False
        self.diagnostics = {}
        self.targets = {}
        self.cleanable = set()

    def __enter__(self):
        return self

    def get(self):
        if self.failed:
            raise ValueError("Chrome connection ended; this session cannot reconnect.")
        if not self.attempted:
            self.attempted = True
            started = time.monotonic()
            phase = "runtime_startup"
            try:
                self.runtime = sync_playwright()
                pw = self.runtime.__enter__()
                # Approval-mode Chrome can listen without a discovery file or JSON endpoint.
                endpoint = f"ws://127.0.0.1:{self.chrome_port}/devtools/browser" if self.chrome_port else "chrome"
                phase = "browser_attachment"
                print("Connecting to Chrome (20-second attachment timeout). If Chrome asks, approve the connection.",
                      file=sys.stderr, flush=True)
                self.browser = pw.chromium.connect_over_cdp(endpoint, timeout=20000, no_defaults=True)
            except (Exception, KeyboardInterrupt) as error:
                self.failed = True
                missing = isinstance(error, PlaywrightError) and "DevToolsActivePort file not found" in str(error)
                self.diagnostics = {
                    "error_code": "chrome_debugging_unavailable" if missing else "chrome_connection_failed",
                    "attachment_elapsed_ms": round((time.monotonic() - started) * 1000),
                    "attachment_phase": phase,
                    "attachment_timeout_ms": 20000,
                    "next_steps": [
                        "Use Chrome 144+ in the same OS and user environment as this CLI; WSL, containers and remote terminals do not automatically discover host Chrome.",
                        "In that Chrome, open chrome://inspect/#remote-debugging and explicitly enable remote debugging if permitted by your organization.",
                        "Enabled debugging can lack a discovery file. If Chrome advertises a port, or its ownership by the intended local Chrome is verified, pass --chrome-port PORT; do not guess a port.",
                        "Keep Chrome visible and approve its connection prompt yourself within the 20-second attachment window. Pending approval is one possible cause, not a confirmed diagnosis.",
                        "If unavailable or still failing, report Chrome version/channel, CLI environment and whether the setting is managed; do not change policy or create a DevToolsActivePort file.",
                    ],
                }
                if isinstance(error, KeyboardInterrupt):
                    raise
                message = ("Chrome debugging connection is unavailable: DevToolsActivePort file not found."
                           if missing else "Chrome connection failed; inspect the browser and sanitized next_steps.")
                raise ValueError(message) from error
        self.check()
        return self.browser

    def check(self):
        if self.browser is not None and not self.browser.is_connected():
            self.failed = True
            self.diagnostics = {"error_code": "chrome_connection_lost"}
            raise ValueError("Chrome connection lost; this session cannot reconnect.")

    def target(self, origin, session, account):
        browser = self.get()
        key = (origin, session, account)
        page = self.targets.get(key)
        if page is not None and not page.is_closed():
            try:
                # stdin can starve Playwright's event loop; drain close/navigation events first.
                page.wait_for_timeout(0)
            except PlaywrightError:
                if not page.is_closed():
                    raise
        if page is None or page.is_closed():
            if len(browser.contexts) != 1:
                raise ValueError("Expected one approved Chrome context; cannot safely choose a profile.")
            page = browser.contexts[0].new_page()
            self.targets[key] = page
            page.set_default_timeout(10000)
            self.diagnostics = {"readiness_phase": "page_navigation"}
            page.goto(origin + "/jira/for-you", wait_until="domcontentloaded", timeout=10000)
        if not page.url.startswith((origin + "/jira/", origin + "/browse/")):
            raise ValueError("CLI tab left the requested Jira site; retained without navigation or refresh.")
        return page

    def __exit__(self, *exc):
        for (origin, _, _), page in self.targets.items():
            try:
                if page.is_closed():
                    continue
                # Only discard our own verified empty legacy panel; unknown state stays visible.
                if page in self.cleanable and page.url.startswith((origin + "/jira/", origin + "/browse/")):
                    panel = resolve_panel(page)
                    if panel is not None and panel.get_attribute("data-testid") == "conversation-assistant.ui.conversation-assistant":
                        require_idle(panel)
                        if (panel.get_by_test_id("rovo-chat-message-group").count() == 0
                                and panel.get_by_test_id("assistant-response-card-layout").count() == 0
                                and page.url.startswith((origin + "/jira/", origin + "/browse/"))):
                            page.close()
                            continue
                print("CLI-created tab retained: empty idle state was not verified.", file=sys.stderr)
            except (Exception, KeyboardInterrupt):
                print("CLI-created tab retained: cleanup could not verify safe closure.", file=sys.stderr)
        browser, runtime = self.browser, self.runtime
        self.browser = self.runtime = None
        self.failed = True
        for cleanup in (browser.close if browser is not None else None,
                        (lambda: runtime.__exit__(*exc)) if runtime is not None else None):
            if cleanup is not None:
                try:
                    cleanup()  # Detach the client; never close external contexts or tabs.
                except (Exception, KeyboardInterrupt):
                    print("Chrome client cleanup failed; original operation result retained.", file=sys.stderr)


def resolve_panel(page):
    panels = [panel for test_id in ("conversation-assistant.ui.conversation-assistant",
                                    "conversation-assistant-mini-modal-main-container")
              for panel in page.get_by_test_id(test_id).all() if panel.is_visible()]
    if len(panels) > 1:
        raise ValueError("Multiple visible Rovo panels in one tab; no tabs changed or prompt sent.")
    return panels[0] if panels else None


def require_idle(panel):
    textbox = panel.get_by_role("textbox")
    if textbox.count() != 1 or not textbox.is_visible() or not textbox.is_enabled():
        raise ValueError("Expected one visible enabled Rovo composer; no prompt sent.")
    draft = textbox.evaluate("""el => { const copy = el.cloneNode(true); copy.querySelectorAll('[data-testid="placeholder-test-id"]').forEach(n => n.remove()); return copy.textContent.trim(); }""")
    if (panel.get_by_role("button", name="Stop generating", exact=True).is_visible() or draft
            or panel.get_by_role("button", name=re.compile(r"^Remove file ")).count()):
        raise ValueError("Existing draft, attachment or active response; no prompt sent.")


def prepare_panel(page, origin, account, diagnostics):
    """Wait for the bound tab, opening its panel once; never reload or retry a send."""
    deadline = time.monotonic() + 10
    opened = more_opened = authenticated = False
    identity = page.get_by_role("button", name=account, exact=True)
    diagnostics.update(readiness_phase="account", readiness_timeout_ms=10000)
    try:
        while True:
            if not page.url.startswith((origin + "/jira/", origin + "/browse/")):
                raise ValueError("CLI tab left the requested Jira site during preparation.")
            if not authenticated:
                if identity.is_visible():
                    authenticated = True
                    if more_opened:
                        page.keyboard.press("Escape")
                        more_opened = False
                else:
                    more = page.get_by_role("button", name="Show more", exact=True)
                    if not more_opened and more.is_visible():
                        more.click(timeout=max(1, int((deadline - time.monotonic()) * 1000)))
                        more_opened = True
            if authenticated:
                diagnostics["readiness_phase"] = "panel"
                panel = resolve_panel(page)
                if panel is not None:
                    diagnostics["readiness_phase"] = "composer"
                    textbox = panel.get_by_role("textbox")
                    if textbox.count() > 1:
                        raise ValueError("Expected one Rovo composer; no prompt sent.")
                    if textbox.count() == 1 and textbox.is_visible():
                        diagnostics["readiness_phase"] = "ready"
                        return panel
                elif not opened:
                    launcher = page.get_by_role("button", name="Ask Rovo", exact=True)
                    if launcher.is_visible() and launcher.is_enabled():
                        launcher.click(timeout=max(1, int((deadline - time.monotonic()) * 1000)))
                        opened = True
            if time.monotonic() >= deadline:
                if diagnostics["readiness_phase"] == "account":
                    return None
                raise ValueError("Rovo panel/composer did not become ready within 10 seconds; tab retained without refresh or submission.")
            page.wait_for_timeout(100)
    finally:
        if more_opened:
            page.keyboard.press("Escape")


def conversation_rows(panel):
    search = panel.get_by_role("searchbox", name="Search conversations...", exact=True)
    if not search.is_visible():
        all_chats = panel.get_by_role("button", name="View all conversations", exact=True)
        if not all_chats.is_visible():
            panel.get_by_role("button", name="Menu", exact=True).click()
        all_chats.click()
    search.wait_for(state="visible")
    if search.input_value():
        raise ValueError("Conversation list has a search filter; clear it before continuing.")
    rows = panel.locator('button[data-testid^="chat-conversation-list-refresh-row-"]')
    # shortcut: loaded history only; an absent or ambiguous new ID disables continuity.
    return rows


def open_conversation(panel, chat_id):
    conversation_rows(panel)
    row = panel.get_by_test_id("chat-conversation-list-refresh-row-" + str(UUID(chat_id)))
    row.wait_for(state="visible")
    row.click()
    panel.get_by_role("searchbox", name="Search conversations...", exact=True).wait_for(state="hidden")
    panel.get_by_role("textbox").wait_for(state="visible")
    panel.get_by_test_id("chat-history-container").locator(".ak-renderer-document").first.wait_for(state="visible")
    require_idle(panel)


def turn_signature(panel):
    groups = panel.get_by_test_id("rovo-chat-message-group")
    last = groups.last
    user = last.locator(".ak-renderer-document").first.inner_text().strip()
    answer = "\n".join(last.get_by_test_id("assistant-response-card-layout").locator(".ak-renderer-document").all_inner_texts()).strip()
    return {"turn_count": groups.count(), "turn_sha256": sha256(json.dumps([user, answer]).encode()).hexdigest()}


def observed_ids(rows):
    ids = rows.evaluate_all("els => els.map(el => el.dataset.testid.replace('chat-conversation-list-refresh-row-', ''))")
    return {str(UUID(value)) for value in ids}


def operate(origin, session, account, prompt=None, timeout=180, images=(), github_source=None,
            chat_id=None, action="status", connection=None, chrome_port=None, new=False):
    allowed_prefixes = (origin + "/jira/", origin + "/browse/")
    directory = state_dir(Path.home(), origin, session)
    record = {"request_id": str(uuid4()), "site": origin, "account": account, "chat_id": chat_id,
              "submission_state": "not_attempted", "execution_status": "prepared"}
    owner = connection
    started_at = lap_at = time.monotonic()
    timings = {}

    def lap(name):
        nonlocal lap_at
        now = time.monotonic()
        timings[name] = round((now - lap_at) * 1000)
        lap_at = now
    base = {"schema_version": 1, "browser_mode": "existing_chrome", "context_percent": None,
            "retrieval_assessment": "unverified", "chat_id": chat_id}
    try:
        with site_lock(directory):
            prior = read_request(directory)
            blocked = blocking_request(directory)
            if blocked:
                return base | blocked | {"execution_status": "blocked", "retry_safe": False,
                                      "message": "Prior delivery remains unresolved. Inspect that conversation; do not resubmit or switch sessions."}, 4
            automatic = prompt is not None and not new and chat_id is None and prior is not None
            if new and chat_id:
                raise ValueError("Use either --new or --chat, not both.")
            if automatic:
                try:
                    if (prior.get("site") != origin or prior.get("account") != account
                            or prior.get("continuity_status") != "verified"):
                        raise ValueError
                    chat_id = str(UUID(prior["chat_id"]))
                except (ValueError, TypeError, AttributeError, KeyError):
                    base["error_code"] = "continuity_unbound"
                    raise ValueError("No verified conversation binding for this session/account. Use --new or an observed --chat UUID.") from None
                record["chat_id"] = chat_id
            base["conversation_mode"] = "continued" if chat_id else "new"
            with (nullcontext(connection) if connection is not None else BrowserConnection(chrome_port)) as owner:
                page = owner.target(origin, session, account)
                lap("attach")
                owner.cleanable.discard(page)
                panel = prepare_panel(page, origin, account, owner.diagnostics)
                lap("prepare")
                base.update(owner.diagnostics, tab_selection="connection_owned", timings_ms=timings)
                if panel is None:
                    return base | record | {"execution_status": "authentication_required", "retry_safe": True}, 2
                if panel.get_attribute("data-testid") == "conversation-assistant-mini-modal-main-container":
                    # shortcut: status only until mini-modal generation and completion are verified.
                    if prompt is None and action == "status":
                        textbox = panel.get_by_role("textbox")
                        if textbox.count() != 1 or not textbox.is_visible():
                            raise ValueError("Expected one visible Rovo composer; no prompt sent.")
                        return base | record | {"execution_status": "completed", "readiness": "authenticated_ui_read_only",
                                               "active_generation": None, "prior_request": prior,
                                               "retry_safe": not unresolved(prior),
                                               "message": "Mini-modal status only; generation, attachments and completion are unverified. Chat actions remain blocked."}, 0
                    base["error_code"] = "rovo_layout_unverified"
                    raise ValueError("Rovo mini-modal detected; generation, attachment and completion controls are unverified. No prompt sent.")
                stop = panel.get_by_role("button", name="Stop generating", exact=True)
                if prompt is None and action == "status":
                    owner.cleanable.add(page)
                    return base | record | {"execution_status": "completed", "readiness": "authenticated_ui",
                                           "active_generation": stop.is_visible(), "prior_request": prior,
                                           "retry_safe": not unresolved(prior)}, 0
                textbox = panel.get_by_role("textbox")
                require_idle(panel)
                responses = panel.get_by_test_id("assistant-response-card-layout")
                if chat_id or action == "chat_list":
                    rows = conversation_rows(panel)
                    if action == "chat_list":
                        rows.first.wait_for(state="visible")
                        chats = rows.evaluate_all("""els => els.slice(0,100).map(el => ({id:el.dataset.testid.replace('chat-conversation-list-refresh-row-',''),title:el.getAttribute('aria-label')}))""")
                        return base | {"execution_status": "completed", "chats": chats,
                                       "coverage": "loaded_only", "truncated": rows.count() > 100}, 0
                    open_conversation(panel, chat_id)
                    if automatic and turn_signature(panel) != {key: prior.get(key) for key in ("turn_count", "turn_sha256")}:
                        base["error_code"] = "conversation_changed"
                        raise ValueError("Saved conversation changed or loaded history differs. Inspect it before explicit --chat continuation; no prompt sent.")
                    if action == "chat_export":
                        turns = panel.get_by_test_id("rovo-chat-message-group").evaluate_all("""els => els.map(el => ({user:el.querySelector('.ak-renderer-document')?.innerText || '',assistant:Array.from(el.querySelectorAll('[data-testid="assistant-response-card-layout"] .ak-renderer-document')).map(n=>n.innerText).join('\\n')}))""")
                        messages, remaining = [], 24000
                        total = sum(len(turn[role]) for turn in turns for role in ("user", "assistant"))
                        for turn in turns:
                            for role in ("user", "assistant"):
                                if turn[role] and remaining > 0:
                                    text = turn[role][:remaining]
                                    messages.append({"role": role, "text": text})
                                    remaining -= len(text)
                        return base | {"execution_status": "completed", "coverage": "loaded_only",
                                       "messages": messages, "truncated": total > 24000,
                                       "attachment_bytes_included": False}, 0
                else:
                    new_chat = panel.get_by_role("button", name="New chat", exact=True)
                    if new_chat.is_enabled():
                        new_chat.click()
                        page.wait_for_function("""() => document.querySelectorAll('[data-testid="assistant-response-card-layout"]').length === 0""")
                    else:
                        welcome = panel.get_by_role("heading", name=re.compile(r"^How can I help(?:, .+)?\?$"))
                        submit = panel.get_by_role("button", name="Submit", exact=True)
                        if (not new_chat.is_visible() or welcome.count() != 1 or not welcome.is_visible()
                                or responses.count() != 0 or panel.get_by_test_id("rovo-chat-message-group").count() != 0
                                or not submit.is_visible() or submit.is_enabled()):
                            raise ValueError("New chat is unavailable; empty-chat state is unverified. No prompt sent.")
                if prompt is not None and not chat_id:
                    old_ids = observed_ids(conversation_rows(panel))
                    panel.get_by_role("button", name="Go back to Rovo chat", exact=True).click()
                    textbox.wait_for(state="visible")
                    if responses.count() or panel.get_by_test_id("rovo-chat-message-group").count():
                        raise ValueError("Expected empty new chat after conversation discovery; no prompt sent.")
                lap("select")
                before = responses.count()
                selected_turn = turn_signature(panel) if chat_id else None
                require_idle(panel)
                if github_source is not None:
                    picker = panel.locator('button[data-spotlight-target="rovo-chat-web-search-spotlight-target"]')
                    picker.click()
                    wanted = github_source == "on"
                    toggle = page.get_by_role("button", name="Select GitHub" if wanted else "Deselect GitHub", exact=True)
                    selected = page.get_by_role("button", name="Deselect GitHub" if wanted else "Select GitHub", exact=True)
                    if wanted:
                        page.get_by_role("checkbox", name="Search company sources", exact=True).check()
                    if toggle.is_visible():
                        toggle.click()
                    selected.wait_for(state="visible")
                    base["github_source_selected"] = wanted
                    picker.click()
                textbox.fill(prompt)
                for attachment in images:
                    panel.get_by_role("button", name="Add", exact=True).click()
                    with page.expect_file_chooser() as chooser:
                        page.get_by_role("menuitem", name="Upload file", exact=True).click()
                    chooser.value.set_files(attachment)
                    panel.get_by_role("button", name="Remove file " + attachment["name"], exact=True).wait_for(state="visible", timeout=30000)
                    panel.get_by_role("button", name=attachment["name"][:-4] + " PNG", exact=True).wait_for(state="visible", timeout=30000)
                if not panel.get_by_role("button", name="Submit", exact=True).is_enabled():
                    raise ValueError("Prompt or attachment is not ready; no prompt sent. Inspect the retained draft.")
                if textbox.inner_text().strip() != prompt.strip() or not page.url.startswith(allowed_prefixes):
                    raise ValueError("Target or draft changed before submission.")
                if (chat_id and turn_signature(panel) != selected_turn) or (not chat_id and responses.count() != before):
                    raise ValueError("Conversation changed before submission; inspect the retained draft.")
                record.update(submission_state="attempted_unknown", execution_status="waiting")
                save_request(directory, record)
                panel.get_by_role("button", name="Submit", exact=True).click()
                # A successful click is not a server acknowledgement; remain conservative.
                deadline = time.monotonic() + timeout
                started = False
                answer = ""
                while time.monotonic() < deadline:
                    if not page.url.startswith(allowed_prefixes):
                        raise ValueError("Browser left the expected site after submission.")
                    status = panel.get_by_test_id("chat-history-status-live-region").inner_text()
                    generating = stop.is_visible()
                    started = started or generating or status.strip() == "Rovo is thinking"
                    count = responses.count()
                    content = responses.last.locator(".ak-renderer-document")
                    answer = "\n".join(content.all_inner_texts()) if count else ""
                    groups = panel.get_by_test_id("rovo-chat-message-group")
                    user_text = groups.last.locator(".ak-renderer-document").first.inner_text() if groups.count() else ""
                    if completed_turn(started=started, count=count, status=status,
                                      generating=generating, answer=answer, before=before,
                                      prompt_matches=user_text.strip() == prompt.strip()):
                        lap("generate")
                        record.update(execution_status="completed", submission_state="observed_submitted")
                        record["continuity_status"] = "unavailable"
                        save_request(directory, record)
                        warnings = []
                        try:
                            signature = {"turn_count": groups.count(),
                                         "turn_sha256": sha256(json.dumps([prompt.strip(), answer.strip()]).encode()).hexdigest()}
                            if turn_signature(panel) != signature:
                                raise ValueError("Completed conversation changed before capture")
                            if not chat_id:
                                require_idle(panel)
                                new_ids = observed_ids(conversation_rows(panel)) - old_ids
                                if len(new_ids) != 1:
                                    raise ValueError("New conversation ID is missing or ambiguous")
                                captured_id = new_ids.pop()
                                open_conversation(panel, captured_id)
                                if turn_signature(panel) != signature:
                                    raise ValueError("Reopened conversation does not match the completed turn")
                                record["chat_id"] = captured_id
                            verified = record | signature | {"continuity_status": "verified"}
                            save_request(directory, verified)
                            record = verified
                        except Exception:
                            warnings.append("Answer completed, but conversation continuity could not be verified. Do not resend; inspect the chat before --chat or use --new for another task.")
                        lap("capture")
                        return base | record | bounded_answer(answer) | {
                            "retry_safe": False, "image_count": len(images), "elapsed_ms": round((time.monotonic()-started_at)*1000),
                            "warnings": warnings}, 0
                    page.wait_for_timeout(200)
                record["execution_status"] = "timeout"
                save_request(directory, record)
                return base | record | {"partial_answer": answer[:12000], "retry_safe": False}, 3
    except (Exception, KeyboardInterrupt) as error:
        # Keep the original attempted_unknown record on disk; never hide uncertainty on failure.
        if owner is not None:
            try:
                owner.check()
            except ValueError:
                pass
            base.update(owner.diagnostics)
        safe = record["submission_state"] == "not_attempted"
        message = str(error).splitlines()[0] if str(error) else "Interrupted"
        # Avoid leaking authentication URLs and Playwright call logs into the result.
        if "http" in message or "ws://" in message:
            message = "Browser operation failed; inspect the local browser without resubmitting."
        return base | record | {"execution_status": "interrupted" if isinstance(error, KeyboardInterrupt) else "error",
                               "message": message[:300], "retry_safe": safe}, 3 if isinstance(error, KeyboardInterrupt) else 1
