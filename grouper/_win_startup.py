"""
_win_startup.py — Suppress Qt companion-window flicker on Windows.

Qt6's Windows platform plugin creates small 188x85 ``QWindowIcon``
windows for taskbar thumbnail integration.  During frameless-window
construction these can briefly flash visible.

This module installs a thread-level ``WH_CBT`` hook that uses two
interception points to suppress both flicker code paths:

- ``HCBT_CREATEWND`` (nCode=3): fires before ``CreateWindowEx`` returns.
  We strip ``WS_VISIBLE`` from the creation style so the window is born
  hidden — this stops the flash that comes from Qt setting the style
  flag directly during window creation.

- ``HCBT_ACTIVATE`` (nCode=5): fires before a window is activated.
  Belt-and-suspenders for any show that still occurs post-creation
  (e.g. ``ShowWindow`` triggered after construction).  Returns non-zero
  to block activation of matching windows.

Both hooks fire *synchronously before* the operation completes, which
is why they work while ``WinEvent`` hooks (post-facto) do not.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from collections.abc import Callable

if sys.platform != "win32":

    def suppress_flicker() -> Callable[[], None]:
        return lambda: None
else:
    user32 = ctypes.windll.user32

    WH_CBT = 5
    HCBT_CREATEWND = 3
    HCBT_ACTIVATE = 5
    WS_VISIBLE = 0x10000000
    GWL_STYLE = -16
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_HIDEWINDOW = 0x0080

    _in_hook: bool = False  # reentrancy guard

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.wintypes.LPARAM,  # return (LRESULT)
        ctypes.c_int,  # nCode
        ctypes.wintypes.WPARAM,  # wParam
        ctypes.wintypes.LPARAM,  # lParam
    )

    # Declare CallNextHookEx with correct 64-bit types
    user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HHOOK,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    user32.CallNextHookEx.restype = ctypes.wintypes.LPARAM

    # CREATESTRUCT mirrors the Windows SDK tagCREATESTRUCTW layout.
    # Fields that are pointers we don't dereference are typed c_void_p to
    # avoid the ATOM-vs-string ambiguity in lpszClass / lpszName.
    # ctypes inserts the required 4-byte padding between style (LONG, 4 B)
    # and lpszName (pointer, 8 B) automatically on 64-bit.
    class CREATESTRUCT(ctypes.Structure):
        _fields_ = [
            ("lpCreateParams", ctypes.c_void_p),
            ("hInstance", ctypes.c_void_p),
            ("hMenu", ctypes.c_void_p),
            ("hwndParent", ctypes.wintypes.HWND),
            ("cy", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("y", ctypes.c_int),
            ("x", ctypes.c_int),
            ("style", ctypes.c_long),
            ("lpszName", ctypes.c_void_p),
            ("lpszClass", ctypes.c_void_p),
            ("dwExStyle", ctypes.wintypes.DWORD),
        ]

    class CBT_CREATEWND(ctypes.Structure):
        _fields_ = [
            ("lpcs", ctypes.POINTER(CREATESTRUCT)),
            ("hwndInsertAfter", ctypes.wintypes.HWND),
        ]

    _hook_handle: int = 0
    _callback_ref: HOOKPROC | None = None  # prevent GC

    def _get_class(hwnd_int: int) -> str:
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ctypes.wintypes.HWND(hwnd_int), cls_buf, 256)
        return cls_buf.value

    def _is_qt_companion(cls: str, cx: int, cy: int) -> bool:
        """Return True if this looks like a small Qt internal companion window.

        Qt's Windows platform plugin registers several companion classes:
          - Qt[56]QWindowIcon          — taskbar thumbnail (188x85)
          - Qt[56]QWindowOwnDCIcon     — window needing its own DC
          - Qt[56]QWindowToolSaveBits  — tool/popup variant
        All have 'QWindow' in their class name.  We match any of them by
        checking for the substring 'QWindow' rather than just 'QWindowIcon',
        and require the window to be small (< 300x200) and use positive dims.
        """
        return 0 < cx < 300 and 0 < cy < 200 and "QWindow" in cls

    def _cbt_hook(nCode: int, wParam: int, lParam: int) -> int:
        global _in_hook
        if _in_hook:
            return user32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)
        _in_hook = True
        try:
            if nCode == HCBT_CREATEWND and wParam and lParam:
                # Strip WS_VISIBLE + move off-screen at creation time.
                # NOTE: Qt creates QWindowIcon windows with cx=0, cy=0 and
                # resizes them later via SetWindowPos, so we do NOT filter by
                # size here — we check class name only.
                try:
                    cbt = ctypes.cast(lParam, ctypes.POINTER(CBT_CREATEWND)).contents
                    lpcs = cbt.lpcs.contents
                    cls = _get_class(wParam)
                    if "QWindow" in cls and lpcs.cx < 800:
                        lpcs.style = lpcs.style & ~WS_VISIBLE
                        lpcs.x = -20000
                        lpcs.y = -20000
                except Exception:
                    pass

            elif nCode == HCBT_ACTIVATE and wParam:
                hwnd = ctypes.wintypes.HWND(wParam)
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                cls = _get_class(wParam)
                if _is_qt_companion(cls, w, h):
                    # Force the window invisible, then block the activation.
                    # Returning 1 alone only blocks keyboard-focus transfer, not
                    # visibility — we must also hide it explicitly.
                    user32.SetWindowPos(
                        hwnd,
                        None,
                        0,
                        0,
                        0,
                        0,
                        SWP_HIDEWINDOW | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    return 1
        finally:
            _in_hook = False

        return user32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

    def suppress_flicker() -> Callable[[], None]:
        """Install the CBT hook.  Returns a cleanup callable."""
        global _hook_handle, _callback_ref
        _callback_ref = HOOKPROC(_cbt_hook)
        _hook_handle = user32.SetWindowsHookExW(
            WH_CBT,
            _callback_ref,
            None,
            ctypes.windll.kernel32.GetCurrentThreadId(),
        )

        def cleanup() -> None:
            global _hook_handle, _callback_ref
            if _hook_handle:
                user32.UnhookWindowsHookEx(_hook_handle)
                _hook_handle = 0
            _callback_ref = None

        return cleanup
