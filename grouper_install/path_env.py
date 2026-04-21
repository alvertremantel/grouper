from __future__ import annotations

import ctypes
import os
import winreg

_HKLM_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def get_machine_path() -> str:
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _HKLM_ENV, 0, winreg.KEY_READ
    ) as key:
        value, _ = winreg.QueryValueEx(key, "Path")
    return str(value)


def set_machine_path(new_value: str) -> None:
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, _HKLM_ENV, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_value)
    _broadcast_setting_change()


def split_path(path_str: str) -> list[str]:
    return [p.strip() for p in path_str.split(";") if p.strip()]


def normalize_path_entry(entry: str) -> str:
    return os.path.normcase(os.path.normpath(entry))


def path_entries_differ(a: str, b: str) -> bool:
    return normalize_path_entry(a) != normalize_path_entry(b)


def add_to_machine_path(directory: str) -> bool:
    current = get_machine_path()
    entries = split_path(current)
    normalized_dir = normalize_path_entry(directory)
    if any(normalize_path_entry(e) == normalized_dir for e in entries):
        return False
    entries.append(directory)
    set_machine_path(";".join(entries))
    return True


def remove_from_machine_path(directory: str) -> bool:
    current = get_machine_path()
    entries = split_path(current)
    normalized_dir = normalize_path_entry(directory)
    filtered = [
        e for e in entries if normalize_path_entry(e) != normalized_dir
    ]
    if len(filtered) == len(entries):
        return False
    set_machine_path(";".join(filtered))
    return True


def _broadcast_setting_change() -> None:
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    TIMEOUT_MS = 5000

    send = ctypes.windll.user32.SendMessageTimeoutW
    send.restype = ctypes.c_bool
    send.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    send(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        TIMEOUT_MS,
        None,
    )
