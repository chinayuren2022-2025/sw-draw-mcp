"""pywin32 pythoncom 的 Linux 测试桩：仅供 import/签名检查，不做任何 COM 调用。"""
VT_EMPTY = 0
VT_I4 = 3
VT_DISPATCH = 9
VT_BOOL = 11
VT_VARIANT = 12
VT_BSTR = 8
VT_ARRAY = 8192
VT_BYREF = 16384


class com_error(Exception):
    pass


def CoInitialize():
    pass


def CoUninitialize():
    pass
