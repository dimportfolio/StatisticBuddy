"""Guard rail: the app must never interact with the game beyond looking at screen pixels.

Fails if any source file uses process/memory access, input simulation, window
messages/hooks, network access or shelling out. The one exception is
capture/window.py, which may ask Windows (read-only) where the game window is.
Keep this passing when adding modules.
"""
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "statisticbuddy"
WINDOW_FINDER = SRC / "capture" / "window.py"

# Never allowed anywhere.
FORBIDDEN = [
    # process / memory access
    r"\bcffi\b", r"\bwin32\w*", r"\bpywin32\b", r"\bpymem\b", r"\bpsutil\b",
    r"ReadProcessMemory", r"WriteProcessMemory", r"OpenProcess", r"VirtualAlloc",
    r"GetWindowThreadProcessId", r"CreateRemoteThread", r"LoadLibrary",
    # input simulation / hooks / talking to windows
    r"\bpyautogui\b", r"\bpynput\b", r"\bkeyboard\b", r"\bmouse\b", r"\bpydirectinput\b",
    r"SendInput", r"keybd_event", r"mouse_event", r"SetWindowsHook", r"PostMessage", r"SendMessage",
    r"SetForegroundWindow", r"SetWindowPos", r"MoveWindow", r"ShowWindow",
    # capturing through the game's window instead of the desktop
    r"PrintWindow", r"GetDC\b",
    # network / external processes
    r"\bsocket\b", r"\brequests\b", r"\burllib\b", r"\bhttp\.client\b", r"\bsubprocess\b",
    r"os\.system", r"QNetwork",
]
# Allowed only in the window finder.
FINDER_ONLY = [r"\bctypes\b", r"\bhwnd\b", r"\buser32\b", r"\bWinDLL\b"]
# The only Windows functions the finder may call: all read-only queries.
FINDER_ALLOWED_CALLS = {
    "EnumWindows", "IsWindowVisible", "IsIconic", "GetWindowTextLengthW", "GetWindowTextW",
    "GetClassNameW", "GetClientRect", "ClientToScreen",
}


def _code_lines(path: Path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        yield n, line.split("#", 1)[0], line


class SafetyTests(unittest.TestCase):
    def test_no_forbidden_apis(self):
        forbidden = re.compile("|".join(FORBIDDEN))
        finder_only = re.compile("|".join(FINDER_ONLY))
        hits = []
        for path in SRC.rglob("*.py"):
            for n, code, line in _code_lines(path):
                if forbidden.search(code) or (path != WINDOW_FINDER and finder_only.search(code)):
                    hits.append(f"{path.relative_to(SRC)}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "Forbidden API used:\n" + "\n".join(hits))

    def test_window_finder_only_reads(self):
        calls = set()
        for _, code, _ in _code_lines(WINDOW_FINDER):
            calls.update(re.findall(r"_user32\.(\w+)", code))
        self.assertTrue(calls, "expected the finder to use user32")
        self.assertLessEqual(calls, FINDER_ALLOWED_CALLS, f"unexpected Windows calls: {calls - FINDER_ALLOWED_CALLS}")

    def test_only_known_links(self):
        # The only web addresses are the Help-menu links, opened in the user's browser on click.
        allowed = {"https://github.com/dimportfolio/StatisticBuddy", "https://buymeacoffee.com/gamedo"}
        found = set()
        for path in SRC.rglob("*.py"):
            for _, code, _ in _code_lines(path):
                found.update(re.findall(r"https?://[^\s\"')]+", code))
        self.assertLessEqual(found, allowed, f"unexpected links: {found - allowed}")

    def test_pixels_come_from_desktop_capture(self):
        screen = (SRC / "capture" / "screen.py").read_text(encoding="utf-8")
        self.assertIn("import mss", screen)


if __name__ == "__main__":
    unittest.main()
