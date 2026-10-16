"""Find where the MapleStory window is on screen.

This only asks Windows for the position, title and class name of top-level
windows, the same read-only queries OBS "Window Capture", Discord and task
switchers use. It never opens the game process, sends it messages, or captures
through its window handle; pixels are still taken from the desktop (see screen.py).

This is the only file allowed to use ctypes (enforced by tests/test_safety.py).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from statisticbuddy.capture.screen import Region

GAME_WINDOW_CLASS = "MapleStoryClass"
DEFAULT_TITLE = "MapleStory"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]


@dataclass(frozen=True)
class GameWindow:
    title: str
    class_name: str
    client: Region  # the game's drawing area in physical screen pixels


def _text(fn, hwnd, size: int) -> str:
    buf = ctypes.create_unicode_buffer(size)
    fn(hwnd, buf, size)
    return buf.value


def find_game_window(title: str = DEFAULT_TITLE) -> GameWindow | None:
    """The visible MapleStory window, or None if it isn't open (or is minimized).

    Matches the game's window class first, then a window whose title is exactly
    ``title``, so a browser tab named "MapleStory | ..." is never picked.
    """
    by_class: list[GameWindow] = []
    by_title: list[GameWindow] = []
    want = title.strip().lower()

    def visit(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return True
        cls = _text(_user32.GetClassNameW, hwnd, 256)
        n = _user32.GetWindowTextLengthW(hwnd)
        name = _text(_user32.GetWindowTextW, hwnd, n + 1) if n else ""
        is_class = cls == GAME_WINDOW_CLASS
        is_title = name.strip().lower() == want
        if not (is_class or is_title):
            return True
        rect = wintypes.RECT()
        pt = wintypes.POINT(0, 0)
        if not _user32.GetClientRect(hwnd, ctypes.byref(rect)) or not _user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return True
        if rect.right < 200 or rect.bottom < 150:
            return True
        win = GameWindow(name, cls, Region(pt.x, pt.y, rect.right, rect.bottom))
        (by_class if is_class else by_title).append(win)
        return True

    _user32.EnumWindows(_EnumProc(visit), 0)
    found = by_class or by_title
    return max(found, key=lambda w: w.client.width * w.client.height) if found else None
