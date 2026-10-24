"""Bounded, opt-in approval of one exclusively owned local Chrome attachment."""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


class ApprovalError(ValueError):
    pass


class ChromeApproval:
    """Keep the native helper alive only while this connection is pending."""

    def __init__(self, port):
        self.port = port
        self.process = None

    def start(self):
        if sys.platform != "darwin" or not self.port:
            raise ApprovalError("Automatic Chrome approval requires macOS and a verified --chrome-port.")
        self.process = subprocess.Popen(
            ["/bin/bash", str(Path(__file__).with_name("allow.sh")), str(os.getpid()), str(self.port)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, start_new_session=True,
        )
        if not select.select([self.process.stdout], [], [], 5)[0]:
            raise ApprovalError("Chrome approval helper did not finish preflight within 5 seconds.")
        self._result(self.process.stdout.readline(), "ready")

    @staticmethod
    def _result(line, expected):
        try:
            result = json.loads(line)
        except (ValueError, TypeError):
            raise ApprovalError("Chrome approval helper returned no valid result.") from None
        # Do not reflect arbitrary helper output into public diagnostics.
        reason = result.get("reason")
        if result.get("status") != expected:
            raise ApprovalError(REASONS.get(reason, "Chrome approval helper failed; nothing was submitted."))

    def finish(self):
        try:
            output, _ = self.process.communicate(b"connected\n", timeout=5)
        except subprocess.TimeoutExpired:
            raise ApprovalError("Chrome approval helper did not finish within 5 seconds.") from None
        self._result(output, "approved")
        if self.process.returncode:
            raise ApprovalError("Chrome approval helper failed; nothing was submitted.")

    def failure(self):
        if self.process is not None and self.process.poll() is not None:
            output, _ = self.process.communicate()
            if output:
                try:
                    self._result(output, "approved")
                except ApprovalError as error:
                    return error
        return None

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                # Only this helper and the native commands it started, never other agents.
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.communicate()


REASONS = {
    "busy": "Chrome approval is ambiguous: another debugging prompt or client is present. Leave it alone; stop other automation before a new read-only connection.",
    "listener": "The verified port must have exactly one normal Google Chrome loopback listener.",
    "dependencies": "Chrome approval needs system Python with Quartz, cliclick, and terminal Accessibility/Automation permissions.",
    "timeout": "No uniquely owned Chrome approval prompt appeared within 17 seconds; nothing was clicked.",
    "changed": "Chrome approval prompt changed or remained open; no additional click is allowed.",
    "cancelled": "Chrome attachment ended before approval; nothing further was clicked.",
}


class GuardFailure(Exception):
    pass


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=3)
    if result.returncode:
        raise GuardFailure("dependencies")
    return result.stdout.strip()


def sockets(port, state):
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-iTCP:" + str(port),
                             "-sTCP:" + state, "-Fpn"], capture_output=True, text=True, timeout=3)
    if result.returncode not in (0, 1) or result.stderr:
        raise GuardFailure("dependencies")
    rows, pid = [], None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n"):
            rows.append((pid, line[1:]))
    return rows


def owned_socket(rows, port, chrome_pid, caller_pid, parents):
    """Require exactly one loopback pair, whose client descends from this CLI."""
    endpoint = "127.0.0.1:" + str(port)
    servers = [(pid, name.split("->", 1)[1]) for pid, name in rows if name.startswith(endpoint + "->")]
    clients = [(pid, name.split("->", 1)[0]) for pid, name in rows if name.endswith("->" + endpoint)]
    if len(rows) != 2 or len(servers) != 1 or len(clients) != 1:
        return False
    if servers[0] != (chrome_pid, clients[0][1]) or not clients[0][1].startswith("127.0.0.1:"):
        return False
    pid, visited = clients[0][0], set()
    while pid and pid not in visited:
        if pid == caller_pid:
            return True
        visited.add(pid)
        pid = parents.get(pid)
    return False


def one_dialog(dialogs, chrome_pid, expected=None):
    if len(dialogs) != 1 or dialogs[0][1] != chrome_pid or (expected and dialogs[0] != expected):
        raise GuardFailure("busy" if expected is None else "changed")
    return dialogs[0]


def worker(caller_pid, port):
    import Quartz

    def dialogs():
        result = []
        for window in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
            if window.get("kCGWindowName") == "Allow remote debugging?":
                b = window["kCGWindowBounds"]
                result.append((int(window["kCGWindowNumber"]), int(window["kCGWindowOwnerPID"]),
                               int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"])))
        return result

    def cancelled():
        if select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if line == "connected\n":
                return True
            raise GuardFailure("cancelled")
        return False

    def check_socket():
        parents = dict(tuple(map(int, line.split())) for line in command(["/bin/ps", "-axo", "pid=,ppid="]).splitlines())
        if not owned_socket(sockets(port, "ESTABLISHED"), port, chrome_pid, caller_pid, parents):
            raise GuardFailure("busy")

    if not os.access("/opt/homebrew/bin/cliclick", os.X_OK):
        raise GuardFailure("dependencies")
    listeners = sockets(port, "LISTEN")
    if len(listeners) != 1 or listeners[0][1] != "127.0.0.1:" + str(port):
        raise GuardFailure("listener")
    chrome_pid = listeners[0][0]
    if not command(["/bin/ps", "-p", str(chrome_pid), "-o", "comm="]).endswith("/Google Chrome.app/Contents/MacOS/Google Chrome"):
        raise GuardFailure("listener")
    if dialogs() or sockets(port, "ESTABLISHED"):
        raise GuardFailure("busy")
    print(json.dumps({"status": "ready"}), flush=True)
    deadline = time.monotonic() + 17
    while time.monotonic() < deadline:
        connected = cancelled()
        current = dialogs()
        connections = sockets(port, "ESTABLISHED")
        if connections:
            check_socket()
        if connected:
            if current:
                raise GuardFailure("busy")
            check_socket()
            return  # The connection completed without needing our click.
        if current:
            selected = one_dialog(current, chrome_pid)
            check_socket()
            command(["/usr/bin/osascript", "-e", 'tell application "Finder" to activate'])
            time.sleep(0.4)
            # Chrome's sheet can move while appearing. Refresh only the same window,
            # before parking the pointer; movement afterward still forbids the click.
            settled = one_dialog(dialogs(), chrome_pid)
            if settled[:2] != selected[:2]:
                raise GuardFailure("changed")
            selected = settled
            check_socket()
            _, _, x, y, width, height = selected
            point = (x + width - 68, y + height - 38)
            command(["/opt/homebrew/bin/cliclick", "m:%s,%s" % point])
            time.sleep(0.4)
            one_dialog(dialogs(), chrome_pid, selected)
            check_socket()
            command(["/usr/bin/osascript", "-e", 'tell application "System Events" to set frontmost of (first process whose unix id is %d) to true' % chrome_pid])
            time.sleep(0.8)
            # Recheck immediately before the sole click. A new/moved dialog is not clicked.
            if cancelled():
                raise GuardFailure("changed")
            check_socket()
            one_dialog(dialogs(), chrome_pid, selected)
            for event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
                event = Quartz.CGEventCreateMouseEvent(None, event_type, point, Quartz.kCGMouseButtonLeft)
                Quartz.CGEventSetIntegerValueField(event, Quartz.kCGMouseEventClickState, 1)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                time.sleep(0.1)
            time.sleep(0.3)
            if dialogs():
                raise GuardFailure("changed")
            check_socket()
            return
        time.sleep(0.1)
    raise GuardFailure("timeout")


if __name__ == "__main__":
    try:
        worker(int(sys.argv[1]), int(sys.argv[2]))
        print(json.dumps({"status": "approved"}), flush=True)
    except Exception as error:
        reason = str(error) if isinstance(error, GuardFailure) else "dependencies"
        print(json.dumps({"status": "error", "reason": reason}), flush=True)
        sys.exit(1)
