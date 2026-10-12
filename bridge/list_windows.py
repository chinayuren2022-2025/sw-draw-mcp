# -*- coding: utf-8 -*-
import ctypes, sys, os
import win32gui, win32process

def proc_image(hwnd):
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        size = ctypes.c_uint(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        ctypes.windll.kernel32.CloseHandle(h)
    return None

items = []
def cb(hwnd, _):
    if not win32gui.IsWindowVisible(hwnd):
        return True
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return True
    cls = win32gui.GetClassName(hwnd)
    img = proc_image(hwnd)
    items.append((hwnd, title, cls, img or ""))
    return True
win32gui.EnumWindows(cb, None)
for hwnd, title, cls, img in sorted(items, key=lambda x: (x[3].lower(), x[2], x[1])):
    print(f"0x{hwnd:08X} cls={cls!r} img={img!r} title={title!r}")
