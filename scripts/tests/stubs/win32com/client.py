"""win32com.client 的 Linux 测试桩：仅供 import/签名检查，不做任何 COM 调用。"""


class VARIANT:
    def __init__(self, vtype=0, value=None):
        self.vtype = vtype
        self.value = value


def Dispatch(obj):
    """后期绑定视图桩：直接返回原对象。"""
    return obj


def GetActiveObject(prog_id):
    raise OSError(f"stub GetActiveObject: {prog_id}")


class gencache:
    @staticmethod
    def EnsureModule(*args, **kwargs):
        raise OSError("stub gencache.EnsureModule")
