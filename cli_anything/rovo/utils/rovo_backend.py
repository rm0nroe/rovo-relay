"""Existing-Chrome Rovo adapter. No cookies, extension install or browser relaunch."""
import time
import re
import sys
from contextlib import contextmanager, nullcontext
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import UUID, uuid4
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit
import json

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright
from cli_anything.rovo.utils.chrome_approval import ApprovalError, ChromeApproval

from cli_anything.rovo.core.state import (
    blocking_request, bounded_answer, completed_turn, delivered, plain, provable, read_request, save_request, site_lock, state_dir, unresolved,
)


class BrowserConnection:
    """Own one lazy CDP attachment; an attempted connection is never retried."""

    def __init__(self, chrome_port=None, approve_chrome_prompt=False):
        self.chrome_port = chrome_port
        self.approve_chrome_prompt = approve_chrome_prompt
        self.browser = None
        self.runtime = None
        self.attempted = False
        self.failed = False
        self.diagnostics = {}
        self.targets = {}
        self.cleanable = set()
        # Tabs whose last operation was a successful list or export, which began idle.
        self.browsed = set()
        # Rovo's own paged history responses per owned tab; see track_history.
        self.history = {}
        # Proof of the chat left open by the last verified ask; consumed by every operation.
        self.warm = None

    def __enter__(self):
        return self

    def get(self):
        if self.failed:
            raise ValueError("Chrome connection ended; this session cannot reconnect.")
        if not self.attempted:
            self.attempted = True
            started = time.monotonic()
            phase = "runtime_startup"
            approval = None
            try:
                self.runtime = sync_playwright()
                pw = self.runtime.__enter__()
                # Approval-mode Chrome can listen without a discovery file or JSON endpoint.
                endpoint = f"ws://127.0.0.1:{self.chrome_port}/devtools/browser" if self.chrome_port else "chrome"
                if self.approve_chrome_prompt:
                    phase = "chrome_approval"
                    approval = ChromeApproval(self.chrome_port)
                    approval.start()
                phase = "browser_attachment"
                notice = ("Guarded approval enabled for this connection only; the pointer and foreground app may move."
                          if approval else "If Chrome asks, approve the connection.")
                print("Connecting to Chrome (20-second attachment timeout). " + notice,
                      file=sys.stderr, flush=True)
                self.browser = pw.chromium.connect_over_cdp(endpoint, timeout=20000, no_defaults=True)
                if approval:
                    phase = "chrome_approval"
                    approval.finish()
            except (Exception, KeyboardInterrupt) as error:
                self.failed = True
                if approval and not isinstance(error, (ApprovalError, KeyboardInterrupt)):
                    error = approval.failure() or error
                approval_failed = isinstance(error, ApprovalError) or phase == "chrome_approval"
                missing = isinstance(error, PlaywrightError) and "DevToolsActivePort file not found" in str(error)
                self.diagnostics = {
                    "error_code": ("chrome_approval_failed" if approval_failed else
                                   "chrome_debugging_unavailable" if missing else "chrome_connection_failed"),
                    "attachment_elapsed_ms": round((time.monotonic() - started) * 1000),
                    "attachment_phase": phase,
                    "attachment_timeout_ms": 20000,
                    "next_steps": [
                        "Use Chrome 144+ in the same OS and user environment as this CLI; WSL, containers and remote terminals do not automatically discover host Chrome.",
                        "In that Chrome, open chrome://inspect/#remote-debugging and explicitly enable remote debugging if permitted by your organization.",
                        "Enabled debugging can lack a discovery file. If Chrome advertises a port, or its ownership by the intended local Chrome is verified, pass --chrome-port PORT; do not guess a port.",
                        ("Keep Chrome visible; the guarded helper handles only this connection. Do not run another helper or repeat the ask."
                         if self.approve_chrome_prompt else
                         "Keep Chrome visible and approve its connection prompt yourself within the 20-second attachment window. Pending approval is one possible cause, not a confirmed diagnosis."),
                        "If unavailable or still failing, report Chrome version/channel, CLI environment and whether the setting is managed; do not change policy or create a DevToolsActivePort file.",
                    ],
                }
                if isinstance(error, KeyboardInterrupt):
                    raise
                if approval_failed:
                    self.diagnostics["next_steps"] = [
                        "Leave other debugging prompts and clients alone. Do not rerun the helper or relaunch an ask.",
                        "Check helper dependencies, permissions and exclusive Chrome availability before a separately authorized read-only status.",
                        "If RemoteDebuggingAllowed is false, report a policy block; never change policy or switch endpoints.",
                    ]
                message = (str(error) if isinstance(error, ApprovalError) else
                           "Chrome approval helper could not run; no prompt was submitted." if approval_failed else
                           "Chrome debugging connection is unavailable: DevToolsActivePort file not found."
                           if missing else "Chrome connection failed; inspect the browser and sanitized next_steps.")
                raise ValueError(message) from error
            finally:
                if approval:
                    approval.close()
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
            page = owned_window_page(browser)
            self.targets[key] = page
            self.history[page] = track_history(page, origin)
            page.set_default_timeout(10000)
            self.diagnostics = {"readiness_phase": "page_navigation"}
            page.goto(origin + "/jira/for-you", wait_until="domcontentloaded", timeout=10000)
        if page_scope(page, origin) == "other":
            raise ValueError("CLI tab left the requested Jira site; retained without navigation or refresh.")
        return page

    def __exit__(self, *exc):
        for (origin, session, _), page in self.targets.items():
            try:
                if page.is_closed():
                    continue
                # Only discard our own idle legacy panel that is verified empty or shows the verified answer.
                if page.url.startswith((origin + "/jira/", origin + "/browse/")):
                    panel = resolve_panel(page)
                    if panel is not None and panel.get_attribute("data-testid") == "conversation-assistant.ui.conversation-assistant":
                        if page in self.browsed:
                            # The picker can hide the composer; only new work since the read-only operation matters.
                            safe = not busy(panel)
                        else:
                            require_idle(panel)
                            safe = ((page in self.cleanable
                                     and panel.get_by_test_id("rovo-chat-message-group").count() == 0
                                     and panel.get_by_test_id("assistant-response-card-layout").count() == 0)
                                    or answered(panel, read_request(state_dir(Path.home(), origin, session))))
                        if safe and page.url.startswith((origin + "/jira/", origin + "/browse/")):
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


class ClickError(ValueError):
    def __init__(self, control, reason, timed_out):
        self.diagnostics = {"control": control, "reason": reason, "timed_out": timed_out}
        super().__init__(f"Click {'timed out' if timed_out else 'failed'}: {control} ({reason}).")


def click_control(locator, control, **kwargs):
    """Click once; control is a fixed code label, never a page title, ID or selector."""
    try:
        locator.click(**kwargs)
    except PlaywrightError as error:
        reason = "unknown"
        header, _, log = str(error).partition("\n")
        if "strict mode violation:" in header:
            reason = "multiple_matches"
        elif "Target page, context or browser has been closed" in header:
            reason = "target_closed"
        # Only emit our vocabulary, never copy DOM previews or locator arguments.
        waiting = resolved = False
        line = ""
        for line in log.splitlines():
            line = re.sub(r"^\s*-\s*(?:\d+\s*×\s*)?", "", line).strip()
            waiting |= bool(re.match(r"waiting for (?:locator|get_by_\w+|getBy\w+)\(", line))
            resolved |= line.startswith("locator resolved to ")
            if line in ("element is not visible", "element is not enabled", "element is not stable"):
                reason = "not_" + line.rsplit(" ", 1)[1]
            elif line == "element is outside of the viewport":
                reason = "outside_viewport"
            elif line == "element was detached from the DOM, retrying":
                reason = "detached"
            elif line.endswith(" intercepts pointer events"):
                reason = "pointer_events_intercepted"
            elif line == "click action done":
                reason = "unknown"
                resolved = True
            elif line == "waiting for scheduled navigations to finish":
                reason = "navigation_pending"
        if reason == "unknown" and waiting and not resolved:
            reason = "locator_not_resolved"
        elif reason == "unknown" and line == "performing click action":
            # Input was sent but the page never acknowledged it (main thread busy, e.g. a sign-in bounce).
            reason = "input_not_acknowledged"
        if reason == "unknown" and page_hidden(locator):
            reason = "page_hidden"
        raise ClickError(control, reason, isinstance(error, PlaywrightTimeoutError)) from None


def page_hidden(locator):
    try:
        return locator.page.evaluate("document.visibilityState") == "hidden"
    except PlaywrightError:
        return False


def owned_window_page(browser):
    """Open the CLI tab in its own unfocused window, never the user's active tab.

    The window sits off-screen but not minimized: hidden pages pause animation frames,
    and Playwright's click stability check then times out."""
    cdp = browser.new_browser_cdp_session()
    try:
        with browser.contexts[0].expect_page() as created:
            target_id = cdp.send("Target.createTarget", {"url": "about:blank", "newWindow": True, "background": True})["targetId"]
        window = cdp.send("Browser.getWindowForTarget", {"targetId": target_id})["windowId"]
        # ponytail: macOS clamps this to a ~40 px sliver on the main display; a display left of it would show the window.
        cdp.send("Browser.setWindowBounds", {"windowId": window, "bounds": {"left": -10000, "top": 0, "width": 1440, "height": 900}})
    finally:
        cdp.detach()
    return created.value


def answered(panel, record):
    """The tab shows exactly the last verified answer, so the saved chat holds everything."""
    return bool(record and record.get("execution_status") == "completed" and record.get("continuity_status") == "verified"
                and shows_turn(turn_signature(panel), record))


def shows_turn(signature, record):
    """The page's last turn is the record's. A virtualized page shows at most the record's turns, never none."""
    return (signature["turn_sha256"] == record.get("turn_sha256")
            and isinstance(record.get("turn_count"), int) and 0 < signature["turn_count"] <= record["turn_count"])


def page_scope(page, origin):
    """Fixed label for where the CLI tab is; never the URL itself."""
    if page.url.startswith((origin + "/jira/", origin + "/browse/")):
        return "jira"
    return "atlassian_identity" if urlsplit(page.url)[:2] == ("https", "id.atlassian.com") else "other"


def resolve_panel(page):
    panels = [panel for test_id in ("conversation-assistant.ui.conversation-assistant",
                                    "conversation-assistant-mini-modal-main-container")
              for panel in page.get_by_test_id(test_id).all() if panel.is_visible()]
    if len(panels) > 1:
        raise ValueError("Multiple visible Rovo panels in one tab; no tabs changed or prompt sent.")
    return panels[0] if panels else None


def busy(panel):
    """Draft, attachment or active response; an absent composer has no draft."""
    textbox = panel.get_by_role("textbox")
    draft = textbox.count() > 1 or (textbox.count() == 1 and textbox.evaluate("""el => { const copy = el.cloneNode(true); copy.querySelectorAll('[data-testid="placeholder-test-id"]').forEach(n => n.remove()); return copy.textContent.trim(); }"""))
    return bool(panel.get_by_role("button", name="Stop generating", exact=True).is_visible() or draft
                or panel.get_by_role("button", name=re.compile(r"^Remove file ")).count())


def require_idle(panel):
    textbox = panel.get_by_role("textbox")
    if textbox.count() != 1 or not textbox.is_visible() or not textbox.is_enabled():
        raise ValueError("Expected one visible enabled Rovo composer; no prompt sent.")
    if busy(panel):
        raise ValueError("Existing draft, attachment or active response; no prompt sent.")


def prepare_panel(page, origin, account, diagnostics):
    """Wait for the bound tab, opening its panel once; never reload or retry a send.

    Returns (panel, opened); opened means the panel was reopened and may show another chat."""
    deadline = time.monotonic() + 10
    opened = more_opened = authenticated = False
    identity = page.get_by_role("button", name=account, exact=True)
    diagnostics.update(readiness_phase="account", readiness_timeout_ms=10000)
    try:
        while True:
            scope = page_scope(page, origin)
            if scope == "other":
                raise ValueError("CLI tab left the requested Jira site during preparation.")
            if scope == "jira":
                diagnostics.pop("page_scope", None)
            else:
                # Atlassian sign-in bounce: wait for Jira without touching the page.
                diagnostics["page_scope"] = scope
            if scope == "jira" and not authenticated:
                if identity.is_visible():
                    # Keep overflow open: it also contains the narrow-window Rovo launcher.
                    authenticated = True
                else:
                    more = page.get_by_role("button", name="Show more", exact=True)
                    if not more_opened and more.is_visible():
                        try:
                            click_control(more, "Show more", timeout=max(1, int((deadline - time.monotonic()) * 1000)))
                        except ClickError:
                            if page_scope(page, origin) != "atlassian_identity":
                                raise
                            diagnostics["page_scope"] = "atlassian_identity"
                        else:
                            more_opened = True
            if scope == "jira" and authenticated:
                diagnostics["readiness_phase"] = "panel"
                panel = resolve_panel(page)
                if panel is not None:
                    diagnostics["readiness_phase"] = "composer"
                    textbox = panel.get_by_role("textbox")
                    if textbox.count() > 1:
                        raise ValueError("Expected one Rovo composer; no prompt sent.")
                    if textbox.count() == 1 and textbox.is_visible():
                        diagnostics["readiness_phase"] = "ready"
                        return panel, opened
                elif not opened:
                    launcher = page.get_by_role("button", name="Ask Rovo", exact=True)
                    if launcher.is_visible() and launcher.is_enabled():
                        click_control(launcher, "Ask Rovo", timeout=max(1, int((deadline - time.monotonic()) * 1000)))
                        opened = True
            if time.monotonic() >= deadline:
                if diagnostics["readiness_phase"] == "account":
                    return None, opened
                raise ValueError("Rovo panel/composer did not become ready within 10 seconds; tab retained without refresh or submission.")
            page.wait_for_timeout(100)
    finally:
        if more_opened and page_scope(page, origin) == "jira":
            page.keyboard.press("Escape")


HISTORY_URL = r"/gateway/api/assist/rovo/v1/chat/(?:conversations|conversation/([0-9a-f-]{36})/messages)(?:\?.*)?"


def message_text(content):
    """Plain text of one Rovo message: markdown as sent, or ADF text with one line per block or hard break."""
    if isinstance(content, str):
        return content
    text = lambda node: ("\n" if node.get("type") == "hardBreak" else node.get("text", "")) + "".join(text(child) for child in node.get("content", []))
    return "\n".join(text(block) for block in content["content"]).strip()


def created(item):
    """Rovo's own timestamp for one message (RFC 1123, to the second), or None when absent or unreadable."""
    try:
        return parsedate_to_datetime(item["time_created"]).timestamp()
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def glued(page, earlier):
    """A chat's messages from one cursor page and the pages before it, in Rovo's own time order,
    whichever way Rovo pages; None when the timestamps cannot place the page."""
    if not page or not earlier:
        return page + earlier
    first, last, before, after = (message.get("time") for message in (page[0], page[-1], earlier[0], earlier[-1]))
    if None in (first, last, before, after):
        return None
    if last <= before:
        return page + earlier
    if after <= first:
        return earlier + page
    return None


def track_history(page, origin):
    """Rovo's own history responses in this tab, keyed None for the chat list or by chat ID:
    whether more exists, how many items arrived since the first page and, for a chat, its messages.
    The chat panel is virtualized, so these responses, not the page, hold a long chat's turns."""
    seen = {}
    pattern = re.compile(re.escape(origin) + HISTORY_URL)

    def record(response):
        match = pattern.fullmatch(response.url)
        if not match or response.request.method != "GET":
            return
        key = match.group(1)
        cursor = "cursor" in parse_qs(urlsplit(response.url).query)
        earlier = seen.get(key, {}) if cursor else {}
        try:
            body = response.json()
            more, items = body["hasNext"] is not False, body["items"]
            messages = [{"id": item.get("id"), "role": item["role"], "text": message_text(item["content"]), "time": created(item)}
                        for item in items] if key else None
        except (PlaywrightError, ValueError, KeyError, TypeError, AttributeError):
            more, items, messages = True, [], None  # Unreadable counts as more history.
        state = {"more": more, "items": earlier.get("items", 0) + len(items)}
        if key:
            older = earlier.get("messages", [])
            if messages is not None and older is not None:
                # A page delivered twice must not duplicate turns.
                ids = {message["id"] for message in older if message["id"]}
                messages = glued([message for message in messages if message["id"] not in ids], older)
            state["messages"] = messages if older is not None else None
        seen[key] = state
    page.on("response", record)
    return seen


def record_turn(history, chat_id, known, prompt, answer, message_id):
    """Add a verified turn to the tab's copy of Rovo's history, which Rovo does not refetch in the same tab.
    Only a copy that held exactly the known turns is extended; a new chat starts from zero."""
    turn = [{"id": None, "role": "HUMAN", "text": prompt.strip()}, {"id": message_id, "role": "ASSISTANT", "text": answer}]
    key = str(UUID(chat_id))
    if known == 0:
        history[key] = {"more": False, "items": 2, "messages": turn}
    elif known is not None and server_turns(history, key) == known:
        history[key] = history[key] | {"items": history[key]["items"] + 2, "messages": history[key]["messages"] + turn}
    else:
        history.pop(key, None)  # Unknown or inconsistent: fall back to what Rovo or the page shows next.


def server_turns(history, chat_id):
    """Turns Rovo returned for this chat, or None unless every page arrived."""
    state = history.get(str(UUID(chat_id)))
    if state and not state["more"] and state.get("messages") is not None:
        return sum(message["role"] == "HUMAN" for message in state["messages"])
    return None


SCROLL_EDGE = """(el, top) => {
  let box = el;
  while (box && !(box.scrollHeight > box.clientHeight && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  if (box) box.scrollTop = top ? 0 : box.scrollHeight;
}"""


def scroll_history(items, top, done, seconds=10):
    """Scroll Rovo's lazy history toward the top or bottom (None: only wait) until done() or time runs out. Never clicks."""
    deadline = time.monotonic() + seconds
    while not done():
        if time.monotonic() >= deadline:
            return
        if top is not None and items.count():
            (items.first if top else items.last).evaluate(SCROLL_EDGE, top)
        # Not time.sleep: waiting here also delivers the response events track_history reads.
        items.page.wait_for_timeout(250)


def list_complete(rows, history):
    state = history.get(None)
    return bool(state) and not state["more"] and rows.count() == state["items"]


def conversation_rows(panel):
    search = panel.get_by_role("searchbox", name="Search conversations...", exact=True)
    if not search.is_visible():
        all_chats = panel.get_by_role("button", name="View all conversations", exact=True)
        if not all_chats.is_visible():
            click_control(panel.get_by_role("button", name="Menu", exact=True), "Menu")
        click_control(all_chats, "View all conversations")
    search.wait_for(state="visible")
    if search.input_value():
        raise ValueError("Conversation list has a search filter; clear it before continuing.")
    return panel.locator('button[data-testid^="chat-conversation-list-refresh-row-"]')


def open_conversation(panel, chat_id, history):
    rows = conversation_rows(panel)
    row = panel.get_by_test_id("chat-conversation-list-refresh-row-" + str(UUID(chat_id)))
    scroll_history(rows, False, lambda: row.is_visible() or list_complete(rows, history))
    row.wait_for(state="visible")
    key = str(UUID(chat_id))
    click_control(row, "Conversation row")
    panel.get_by_role("searchbox", name="Search conversations...", exact=True).wait_for(state="hidden")
    panel.get_by_role("textbox").wait_for(state="visible")
    panel.get_by_test_id("chat-history-container").locator(".ak-renderer-document").first.wait_for(state="visible")
    groups = panel.get_by_test_id("rovo-chat-message-group")
    # Rovo fetches a chat once per tab; a reopen serves its cache, which record_turn keeps current.
    scroll_history(groups, None, lambda: key in history, seconds=3)
    if key in history and history[key]["more"]:
        # Older pages load as the history scrolls up; return to the newest turn for the signature.
        scroll_history(groups, True, lambda: not history[key]["more"])
        groups.last.evaluate(SCROLL_EDGE, False)
        panel.page.wait_for_timeout(250)
    require_idle(panel)


def turn_signature(panel):
    groups = panel.get_by_test_id("rovo-chat-message-group")
    last = groups.last
    user = plain(last.locator(".ak-renderer-document").first.inner_text())
    answer = "\n".join(last.get_by_test_id("assistant-response-card-layout").locator(".ak-renderer-document").all_inner_texts()).strip()
    return {"turn_count": groups.count(), "turn_sha256": sha256(json.dumps([user, answer]).encode()).hexdigest()}


def last_message_id(panel):
    """Server-assigned UUID of the last message group, or None when absent or ambiguous."""
    ids = panel.get_by_test_id("rovo-chat-message-group").last.locator("[data-message-id]")
    try:
        return str(UUID(ids.get_attribute("data-message-id"))) if ids.count() == 1 else None
    except (TypeError, ValueError):
        return None


def warm_tab(panel, page, warm, prior, opened):
    """Reuse the open chat only on proof it is the one just verified; anything else uses the picker.
    Returns the page's turn signature as that proof, or None."""
    if (prior is None or warm is None or opened or warm["page"] is not page
            or warm["request_id"] != prior.get("request_id")
            or panel.get_by_role("searchbox", name="Search conversations...", exact=True).is_visible()):
        return None
    # Count first: turn_signature on zero groups would wait out the locator timeout.
    if not panel.get_by_test_id("rovo-chat-message-group").count():
        return None
    signature = turn_signature(panel)
    return signature if shows_turn(signature, prior) and last_message_id(panel) == warm["message_id"] else None


OBSERVE_TURN = """panel => {
  const all = (root, selector) => Array.from(root.querySelectorAll(selector));
  const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const label = el => (el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') || '').trim();
  const statuses = all(panel, '[data-testid="chat-history-status-live-region"]');
  if (statuses.length > 1) throw new Error('Multiple Rovo status regions');
  const responses = all(panel, '[data-testid="assistant-response-card-layout"]');
  const groups = all(panel, '[data-testid="rovo-chat-message-group"]');
  const user = groups.length ? groups[groups.length - 1].querySelector('.ak-renderer-document') : null;
  const ids = groups.length ? all(groups[groups.length - 1], '[data-message-id]') : [];
  return {
    status: statuses.length ? statuses[0].innerText : '',
    generating: all(panel, 'button, [role="button"]').some(el => label(el) === 'Stop generating' && visible(el)),
    count: responses.length,
    // This turn's own cards: until it renders one, the panel's last card is the previous answer.
    answer: groups.length ? all(groups[groups.length - 1], '[data-testid="assistant-response-card-layout"] .ak-renderer-document').map(el => el.innerText).join('\\n') : '',
    group_count: groups.length,
    user_text: user ? user.innerText : '',
    last_id: ids.length === 1 ? ids[0].dataset.messageId : null,
  };
}"""


WAIT_TURN = """(panel, {before, prompt, ms, old_ids}) => new Promise((resolve, reject) => {
  const observe = """ + OBSERVE_TURN + """;
  // Same as state.plain: non-blank lines, spaces collapsed.
  const plain = text => text.split(/\\r\\n|[\\n\\r]/).map(line => line.trim().split(/\\s+/).join(' ')).filter(Boolean).join('\\n');
  let started = false, timer, observer;
  const finish = (turn, error) => { observer.disconnect(); clearTimeout(timer); error ? reject(error) : resolve(turn); };
  // Same rules as completed_turn, which stays the authoritative check; this only decides when to return.
  const check = last => {
    let turn;
    try { turn = observe(panel); } catch (error) { return finish(null, error); }
    started = started || turn.generating || turn.status.trim() === 'Rovo is thinking';
    const fresh = turn.count > before || (turn.last_id && !old_ids.includes(turn.last_id));
    if (last || (started && fresh && plain(turn.user_text) === prompt
        && turn.status.trim() === 'Response complete.' && !turn.generating && turn.answer.trim())) {
      finish({...turn, started});
    }
  };
  observer = new MutationObserver(() => check(false));
  observer.observe(panel, {subtree: true, childList: true, characterData: true, attributes: true});
  timer = setTimeout(() => check(true), ms);
  check(false);
})"""


def wait_turn(panel, before, prompt, ms, old_ids=()):
    """One consistent read of the completion fields, taken as soon as the page shows a completed
    turn or after ms. "started" reports a start seen at any moment during the wait."""
    return panel.evaluate(WAIT_TURN, {"before": before, "prompt": plain(prompt), "ms": ms, "old_ids": list(old_ids)})


SEND_URL = (r"/gateway/api/assist/rovo/v1/chat/conversation/"
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/message/stream(?:/sse)?")


@contextmanager
def watch_sends(page, origin):
    """Conversation IDs named by this tab's Rovo send requests while the block runs.

    The send request streams the answer and never finishes, so read it as it starts."""
    sends = []
    pattern = re.compile(re.escape(origin) + SEND_URL)

    def record(request):
        match = pattern.fullmatch(request.url)
        if request.method == "POST" and match:
            sends.append(match.group(1))
    page.on("request", record)
    try:
        yield sends
    finally:
        page.remove_listener("request", record)


def operate(origin, session, account, prompt=None, timeout=180, images=(), github_source=None,
            chat_id=None, action="status", connection=None, chrome_port=None, new=False, approve_chrome_prompt=False):
    allowed_prefixes = (origin + "/jira/", origin + "/browse/")
    directory = state_dir(Path.home(), origin, session)
    record = {"request_id": str(uuid4()), "site": origin, "account": account, "chat_id": chat_id,
              "submission_state": "not_attempted", "execution_status": "prepared"}
    owner = connection
    warm = None
    if connection is not None:
        warm, connection.warm = connection.warm, None
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

            def refused(reason):
                return base | prior | {"execution_status": "blocked", "retry_safe": False, "reconcilable": False, "reconcile_reason": reason,
                                       "message": "Delivery is still unproven; the block stays. Inspect that conversation; do not resubmit or switch sessions."}, 4
            if action == "reconcile":
                # Reconcile only reads Rovo, so it runs past the block it exists to resolve, and only on this session's record.
                if not unresolved(prior):
                    return base | {"execution_status": "error", "error_code": "reconcile_not_needed", "retry_safe": False,
                                   "message": "This session has no uncertain delivery to reconcile."}, 1
                if not provable(prior):
                    return refused("record_unprovable")
                record, chat_id = prior, prior["chat_id"]
            blocked = action != "reconcile" and blocking_request(directory)
            if blocked:
                own = blocked.get("request_id") == (prior or {}).get("request_id") and provable(blocked)
                return base | blocked | {"execution_status": "blocked", "retry_safe": False, "reconcilable": own,
                                      "message": ("Prior delivery remains unresolved. Run reconcile for this session; never resubmit." if own else
                                                  "Prior delivery remains unresolved. Inspect that conversation; do not resubmit or switch sessions.")}, 4
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
            with (nullcontext(connection) if connection is not None else BrowserConnection(chrome_port, approve_chrome_prompt)) as owner:
                page = owner.target(origin, session, account)
                lap("attach")
                owner.cleanable.discard(page)
                owner.browsed.discard(page)
                panel, opened = prepare_panel(page, origin, account, owner.diagnostics)
                lap("prepare")
                base.update(owner.diagnostics, tab_selection="connection_owned", timings_ms=timings)
                if panel is None:
                    return base | record | {"execution_status": "authentication_required",
                                            "retry_safe": record["submission_state"] == "not_attempted"}, 2
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
                # Recheck idle only after an unchecked click (open_conversation checks its own); reads cannot change it.
                idle_checked = True
                selected_turn = known = None
                responses = panel.get_by_test_id("assistant-response-card-layout")
                history = owner.history.get(page, {})
                proof = warm_tab(panel, page, warm, prior if automatic else None, opened) if chat_id else None
                if proof:
                    base["chat_selection"] = "warm_tab"
                    # The page's own signature for the pre-submit recheck; a virtualized page shows fewer turns than prior counts.
                    selected_turn, known = proof, prior.get("turn_count")
                elif chat_id or action == "chat_list":
                    if chat_id:
                        base["chat_selection"] = "picker"
                    rows = conversation_rows(panel)
                    if action == "chat_list":
                        scroll_history(rows, False, lambda: list_complete(rows, history) or rows.count() > 100)
                        chats = rows.evaluate_all("""els => els.slice(0,100).map(el => ({id:el.dataset.testid.replace('chat-conversation-list-refresh-row-',''),title:el.getAttribute('aria-label')}))""")
                        complete, truncated = list_complete(rows, history), rows.count() > 100
                        # The open picker hides the composer, which the next operation in a session waits for.
                        click_control(panel.get_by_role("button", name="Go back to Rovo chat", exact=True), "Go back to Rovo chat")
                        panel.get_by_role("searchbox", name="Search conversations...", exact=True).wait_for(state="hidden")
                        owner.browsed.add(page)
                        return base | {"execution_status": "completed", "chats": chats,
                                       "coverage": "complete" if complete else "loaded_only", "truncated": truncated}, 0
                    open_conversation(panel, chat_id, history)
                    # The panel is virtualized: count turns from Rovo's data when all of it arrived.
                    known = server_turns(history, chat_id)
                    if automatic:
                        selected_turn = turn_signature(panel)
                        # A virtualized page shows at most Rovo's count; none or more than that is a change.
                        counted = selected_turn | ({"turn_count": known} if known is not None and 0 < selected_turn["turn_count"] <= known else {})
                        if counted != {key: prior.get(key) for key in ("turn_count", "turn_sha256")}:
                            base["error_code"] = "conversation_changed"
                            raise ValueError("Saved conversation changed or loaded history differs. Inspect it before explicit --chat continuation; no prompt sent.")
                    if action == "reconcile":
                        state = history.get(str(UUID(chat_id))) or {}
                        reply, reason = ((None, "history_incomplete") if state.get("messages") is None or state["more"] else
                                         delivered(state["messages"], prior["prompt_sha256"], prior["turns_before"]))
                        owner.browsed.add(page)
                        if reply is None:
                            return refused(reason)
                        record = prior | {"execution_status": "completed", "submission_state": "observed_submitted",
                                          "continuity_status": "unavailable",
                                          "reconciled": {"evidence": "rovo_messages", "message_id": reply["id"], "original": prior}}
                        save_request(directory, record)
                        return base | record | bounded_answer(reply["text"]) | {"retry_safe": False}, 0
                    if action == "chat_export":
                        state = history.get(str(UUID(chat_id))) or {}
                        if state.get("messages") is not None:
                            roles = {"HUMAN": "user", "ASSISTANT": "assistant"}
                            pairs = [(roles[m["role"]], m["text"]) for m in state["messages"] if m["role"] in roles]
                            complete = not state["more"]
                        else:
                            # Without Rovo's data only the turns the virtualized panel shows are readable.
                            turns = panel.get_by_test_id("rovo-chat-message-group").evaluate_all("""els => els.map(el => ({user:el.querySelector('.ak-renderer-document')?.innerText || '',assistant:Array.from(el.querySelectorAll('[data-testid="assistant-response-card-layout"] .ak-renderer-document')).map(n=>n.innerText).join('\\n')}))""")
                            pairs = [(role, turn[role]) for turn in turns for role in ("user", "assistant")]
                            complete = False
                        messages, remaining = [], 24000
                        total = sum(len(text) for _, text in pairs)
                        for role, text in pairs:
                            if text and remaining > 0:
                                messages.append({"role": role, "text": text[:remaining]})
                                remaining -= len(text[:remaining])
                        owner.browsed.add(page)
                        return base | {"execution_status": "completed", "coverage": "complete" if complete else "loaded_only",
                                       "messages": messages, "truncated": total > 24000,
                                       "attachment_bytes_included": False}, 0
                else:
                    new_chat = panel.get_by_role("button", name="New chat", exact=True)
                    if new_chat.is_enabled():
                        click_control(new_chat, "New chat")
                        idle_checked = False
                        page.wait_for_function("""() => document.querySelectorAll('[data-testid="assistant-response-card-layout"]').length === 0""")
                    else:
                        welcome = panel.get_by_role("heading", name=re.compile(r"^How can I help(?:, .+)?\?$"))
                        submit = panel.get_by_role("button", name="Submit", exact=True)
                        if (not new_chat.is_visible() or welcome.count() != 1 or not welcome.is_visible()
                                or responses.count() != 0 or panel.get_by_test_id("rovo-chat-message-group").count() != 0
                                or not submit.is_visible() or submit.is_enabled()):
                            raise ValueError("New chat is unavailable; empty-chat state is unverified. No prompt sent.")
                lap("select")
                before = responses.count()
                # Message IDs the chat already has: a different one on the last turn is a new turn.
                old_ids = {last_message_id(panel)} | {message["id"] for message in
                                                      (history.get(str(UUID(chat_id)), {}).get("messages") or [] if chat_id else [])}
                old_ids.discard(None)
                if chat_id and selected_turn is None:
                    selected_turn = turn_signature(panel)
                if not idle_checked:
                    require_idle(panel)
                if github_source is not None:
                    picker = panel.locator('button[data-spotlight-target="rovo-chat-web-search-spotlight-target"]')
                    click_control(picker, "Source picker (open)")
                    wanted = github_source == "on"
                    toggle = page.get_by_role("button", name="Select GitHub" if wanted else "Deselect GitHub", exact=True)
                    selected = page.get_by_role("button", name="Deselect GitHub" if wanted else "Select GitHub", exact=True)
                    if wanted:
                        page.get_by_role("checkbox", name="Search company sources", exact=True).check()
                    if toggle.is_visible():
                        click_control(toggle, "Select GitHub" if wanted else "Deselect GitHub")
                    selected.wait_for(state="visible")
                    base["github_source_selected"] = wanted
                    click_control(picker, "Source picker (close)")
                textbox.fill(prompt)
                for attachment in images:
                    click_control(panel.get_by_role("button", name="Add", exact=True), "Add")
                    with page.expect_file_chooser() as chooser:
                        click_control(page.get_by_role("menuitem", name="Upload file", exact=True), "Upload file")
                    chooser.value.set_files(attachment)
                    panel.get_by_role("button", name="Remove file " + attachment["name"], exact=True).wait_for(state="visible", timeout=30000)
                    panel.get_by_role("button", name=attachment["name"][:-4] + " PNG", exact=True).wait_for(state="visible", timeout=30000)
                if not panel.get_by_role("button", name="Submit", exact=True).is_enabled():
                    raise ValueError("Prompt or attachment is not ready; no prompt sent. Inspect the retained draft.")
                if plain(textbox.inner_text()) != plain(prompt) or not page.url.startswith(allowed_prefixes):
                    raise ValueError("Target or draft changed before submission.")
                if (chat_id and turn_signature(panel) != selected_turn) or (not chat_id and responses.count() != before):
                    raise ValueError("Conversation changed before submission; inspect the retained draft.")
                # What reconcile needs to prove delivery later: the prompt's hash and Rovo's own turn count
                # (never the virtualized page's), or None when Rovo's data is missing.
                record.update(submission_state="attempted_unknown", execution_status="waiting",
                              prompt_sha256=sha256(plain(prompt).encode()).hexdigest(),
                              turns_before=server_turns(history, chat_id) if chat_id else 0)
                save_request(directory, record)
                with watch_sends(page, origin) as sends:
                    click_control(panel.get_by_role("button", name="Submit", exact=True), "Submit")
                    # A successful click is not a server acknowledgement; remain conservative.
                    deadline = time.monotonic() + timeout
                    started = False
                    answer = ""
                    while time.monotonic() < deadline:
                        if not page.url.startswith(allowed_prefixes):
                            raise ValueError("Browser left the expected site after submission.")
                        # ponytail: site-left and deadline are noticed once per slice (up to 1 s), not every 200 ms;
                        # a navigation rejects the wait at once. Shorten the slice if that lag matters.
                        try:
                            turn = wait_turn(panel, before, prompt, round(min(1, deadline - time.monotonic()) * 1000), old_ids)
                        except PlaywrightError:
                            if not page.url.startswith(allowed_prefixes):
                                raise ValueError("Browser left the expected site after submission.")
                            raise
                        status, generating = turn["status"], turn["generating"]
                        new_id = bool(turn.get("last_id")) and turn.get("last_id") not in old_ids
                        prompt_matches = plain(turn["user_text"]) == plain(prompt)
                        # Until this turn's group renders, the last group is the previous turn.
                        answer = turn["answer"] if (turn["count"] > before or new_id) and prompt_matches else ""
                        started = started or turn["started"] or generating or status.strip() == "Rovo is thinking"
                        if completed_turn(started=started, count=turn["count"], status=status,
                                          generating=generating, answer=answer, before=before,
                                          prompt_matches=prompt_matches, new_id=new_id):
                            lap("generate")
                            record.update(execution_status="completed", submission_state="observed_submitted")
                            record["continuity_status"] = "unavailable"
                            save_request(directory, record)
                            warnings = []
                            try:
                                signature = {"turn_count": turn["group_count"],
                                             "turn_sha256": sha256(json.dumps([plain(prompt), answer.strip()]).encode()).hexdigest()}
                                if turn_signature(panel) != signature:
                                    raise ValueError("Completed conversation changed before capture")
                                if not chat_id:
                                    # Exactly one send from this tab after our Submit names the new chat.
                                    if len(sends) != 1:
                                        raise ValueError("New conversation ID is missing or ambiguous")
                                    record["chat_id"] = sends[0]
                                # A virtualized panel undercounts a long chat; Rovo's count at selection plus this turn does not.
                                saved = signature | ({"turn_count": known + 1} if chat_id and known is not None else {})
                                verified = record | saved | {"continuity_status": "verified"}
                                save_request(directory, verified)
                                record = verified
                                message_id = last_message_id(panel)
                                record_turn(history, record["chat_id"], known if chat_id else 0, prompt, answer, message_id)
                                if message_id:
                                    owner.warm = {"page": page, "request_id": record["request_id"], "message_id": message_id}
                            except Exception:
                                warnings.append("Answer completed, but conversation continuity could not be verified. Do not resend; inspect the chat before --chat or use --new for another task.")
                            lap("capture")
                            return base | record | bounded_answer(answer) | {
                                "retry_safe": False, "image_count": len(images), "elapsed_ms": round((time.monotonic()-started_at)*1000),
                                "warnings": warnings}, 0
                    record["execution_status"] = "timeout"
                    if not chat_id and len(sends) == 1:
                        # The one send from this tab names the new chat, so reconcile can find it.
                        record["chat_id"] = sends[0]
                    save_request(directory, record)
                    return base | record | {"partial_answer": answer[:12000], "retry_safe": False}, 3
    except (Exception, KeyboardInterrupt) as error:
        # Keep the original attempted_unknown record on disk; never hide uncertainty on failure.
        if isinstance(error, ClickError):
            base["click_diagnostics"] = error.diagnostics
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
