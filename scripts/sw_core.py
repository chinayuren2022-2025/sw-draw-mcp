"""sw_core.py — SolidWorks COM 通信层（第3层底层）

职责：连接、新建/保存文档、单位换算、质量属性、选择辅助、重建与错误回读。
模式参考 solidworks-automation-skill (MIT) 已验证写法。

v2 新增（补全清单 2.x）：
    - TLB 版本自适应（RevisionNumber → makepy 次版本）
    - 统一 errors/warnings VARIANT 回读
    - 特征树遍历、文档打开/复用、模型重建
    - 参数数量类 COM 错误识别（供各特征模块做多签名回退）
"""
import glob
import os
import time

import pythoncom
import win32com.client
from win32com.client import VARIANT

# 本机 SolidWorks 类型库主 GUID；次版本 26 = SW 2018（其他版本按 RevisionNumber 调整）
_SW_TLB = ["{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 26, 0]
_mod = None
_mod_minor = None

# swUserPreferenceStringValue_e
_SW_DEFAULT_TEMPLATE_PART = 8
_SW_DEFAULT_TEMPLATE_ASSEMBLY = 9
_SW_DEFAULT_TEMPLATE_DRAWING = 10
# “文件位置 > 文件模板”搜索目录列表（分号分隔）
_SW_TEMPLATE_SEARCH_FOLDERS = 6
# 关闭新建文档模板选择弹窗
_SW_ALWAYS_USE_DEFAULT_TEMPLATES = 111
# 图纸模板落盘兜底时的图幅偏好：gb_a0..gb_a4p 按字母序 A0 排第一，
# 直接取首个会让每张图都变成 1189x841。
_DRAWING_TEMPLATE_PREFERENCE = ("a3", "a4", "a2", "a1", "a0")
# 模板扩展名 -> 默认模板首选项槽位
_TEMPLATE_PREF_SLOT = {
    ".prtdot": _SW_DEFAULT_TEMPLATE_PART,
    ".asmdot": _SW_DEFAULT_TEMPLATE_ASSEMBLY,
    ".drwdot": _SW_DEFAULT_TEMPLATE_DRAWING,
}


def _early_module(minor=None):
    """加载 makepy 早绑定模块；失败返回 None（回退后期绑定）。

    minor=None 时使用当前缓存次版本；minor 给定时先按给定版本 EnsureModule。
    """
    global _mod, _mod_minor
    use_minor = minor if minor is not None else _SW_TLB[2]
    if _mod is not None and _mod_minor == use_minor:
        return _mod
    if _mod is None or _mod_minor != use_minor:
        try:
            from win32com.client import gencache
            _mod = gencache.EnsureModule(_SW_TLB[0], _SW_TLB[1], use_minor, _SW_TLB[3])
            _mod_minor = use_minor
        except Exception:
            _mod = False
            _mod_minor = use_minor
    return _mod or None


def tlb_minor_for_sw(sw=None):
    """根据 SolidWorks 版本推导类型库次版本。

    规则（README 安装第 3 步）：次版本 = SW 年份 - 2000 + 8。
    RevisionNumber 形如 "SolidWorks 2018 SP5" / "26,5"，解析失败回退 26（SW2018）。
    """
    rev = None
    if sw is not None:
        try:
            rev = str(sw.RevisionNumber())
        except Exception:
            rev = None
    year = None
    if rev:
        import re
        m = re.search(r"20(\d{2})", rev)
        if m:
            year = 2000 + int(m.group(1))
    if year is None:
        return _SW_TLB[2]
    return (year - 2000) + 8


def ensure_tlb(sw=None):
    """连接后调用：让 _early 包装使用与当前 SW 匹配的类型库次版本。"""
    minor = tlb_minor_for_sw(sw)
    global _SW_TLB
    _SW_TLB[2] = minor
    return minor


def _early(obj, cls_name):
    """把 COM 对象包装/转换成早绑定类；模块不可用时原样返回。

    仅当对象已经是目标生成类实例时直接返回（避免二次包装破坏 vtable）；
    其它情况仍做接口转换（如 IModelDoc2 -> IPartDoc）。
    """
    if obj is None:
        return obj
    mod = _early_module(_SW_TLB[2])
    if mod is None:
        return obj
    try:
        cls = getattr(mod, cls_name)
    except Exception:
        return obj
    try:
        if isinstance(obj, cls):
            return obj
    except Exception:
        pass
    try:
        return cls(obj._oleobj_)
    except Exception:
        return obj


def com_get(obj, name, *args):
    """兼容 pywin32 后期绑定下“属性/方法”二义性。"""
    member = getattr(obj, name)
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as exc:
        if "-2147352573" in str(exc) or "Member not found" in str(exc):
            return member
        raise


def com_set(obj, name, value):
    """后期绑定下设置 COM 属性（早绑定对象可直接赋值，此函数两种都兼容）。"""
    try:
        setattr(obj, name, value)
    except Exception:
        obj._oleobj_.Invoke(obj._oleobj_.GetIDsOfNames(name)[0], 0x4, 4, 0, value)


def mm(v):
    """毫米 → 米（SW API 内部单位）。"""
    return float(v) / 1000.0


def rad(deg):
    """角度 → 弧度（SW API 内部单位）。"""
    import math
    return math.radians(float(deg))


def _dyn(obj):
    """取后期绑定视图（早/后期绑定对象通用），用于 VARIANT 参数的调用。"""
    return win32com.client.Dispatch(obj._oleobj_)


def _empty_callout():
    """SelectByID2 的 Callout 参数在部分 SW 版本不接受 None，需空 Dispatch。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def err_variants():
    """统一的 errors/warnings ByRef 输出参数对。"""
    return (VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0))


def is_arg_count_error(exc):
    """识别“参数数量/成员不存在”类 COM 错误，供多签名回退使用。"""
    s = str(exc)
    return any(k in s for k in ("Invalid number of parameters", "参数数量",
                                "Wrong number", "Type mismatch", "类型不匹配",
                                "Member not found", "0x8002000e", "0x80020005",
                                "0x80020003", "-2147352562", "-2147352571",
                                "-2147352573"))


def call_sigs(obj, method, sigs, desc):
    """按候选签名依次调用方法，跳过“签名不匹配”类错误。

    sigs: [(args...), ...]；任一次返回非 None 即成功并返回结果。
    全部失败抛出 RuntimeError，附最后一次异常。
    """
    last = None
    for args in sigs:
        try:
            ret = getattr(obj, method)(*args)
            if ret is not None:
                return ret
            last = RuntimeError(f"{desc}: {method} 返回 None")
        except Exception as exc:
            last = exc
            if not is_arg_count_error(exc):
                raise RuntimeError(f"{desc}: {method} 调用失败: {exc}") from exc
    raise RuntimeError(f"{desc}: {method} 所有候选签名均失败: {last}")


def connect(version=None, visible=True):
    """附着到运行中的 SW，失败则启动新实例。返回 sw 应用对象。"""
    try:
        sw = win32com.client.GetActiveObject("SldWorks.Application")
        print("[sw_core] 已附着到运行中的 SolidWorks")
    except Exception:
        prog_id = "SldWorks.Application"
        if version:
            prog_id = f"SldWorks.Application.{(version - 2000) + 8}"
        sw = win32com.client.Dispatch(prog_id)
        sw.Visible = visible
        time.sleep(5)
        print(f"[sw_core] 已启动新 SolidWorks 实例 ({prog_id})")
    ensure_tlb(sw)
    return _early(sw, "ISldWorks")


def _pref_str(sw, index):
    """读取一个字符串首选项槽位，读不到时返回空串。"""
    try:
        return str(sw.GetUserPreferenceStringValue(index) or "").strip().strip('"')
    except Exception:
        return ""


def _pick_template_in_dir(folder, ext):
    r"""在 folder 里挑一个 ext 模板；不递归。

    子目录 templates\MBD 放的是按尺寸分档的专用模板
    （part 0001mm and smaller.prtdot），不适合当默认值。
    """
    if not folder or not os.path.isdir(folder):
        return None
    hits = sorted(glob.glob(os.path.join(folder, "*" + ext)))
    if not hits:
        return None
    if ext.lower() == ".drwdot":
        for token in _DRAWING_TEMPLATE_PREFERENCE:
            for hit in hits:
                if token in os.path.basename(hit).lower():
                    return hit
    return hits[0]


def _installed_template_dirs(sw):
    """按当前挂接的 SW 版本排序的模板安装目录（新版在前）。"""
    year = None
    try:
        minor = tlb_minor_for_sw(sw)
        year = 2000 + (minor - 8)
    except Exception:
        year = None

    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")

    dirs = []
    if year:
        dirs.append(os.path.join(program_data, "SolidWorks",
                                 "SOLIDWORKS %d" % year, "templates"))
    # 一台机器上常并存多个版本，字母序会挑到最老的那个，所以倒序。
    dirs += sorted(glob.glob(os.path.join(program_data, "SolidWorks",
                                          "SOLIDWORKS *", "templates")),
                   reverse=True)
    dirs += sorted(glob.glob(os.path.join(program_files, "SOLIDWORKS Corp",
                                          "SOLIDWORKS*", "lang", "*")))
    return dirs


def find_template(sw, ext):
    r"""找一个真实存在的 ext 模板（.prtdot/.asmdot/.drwdot）。

    顺序：默认模板首选项 -> 模板搜索目录 -> 当前版本的安装模板目录。
    首选项里的路径必须真的存在才用：SW2018 这台机器的默认零件模板指向
    templates\零件.prtdot，而安装里只有 gb_part.prtdot，指过去 NewDocument
    直接返回 None。
    """
    ext = ext.lower()
    slot = _TEMPLATE_PREF_SLOT.get(ext)

    if slot is not None:
        for cand in _pref_str(sw, slot).split(";"):
            cand = os.path.expandvars(cand.strip().strip('"'))
            if not cand:
                continue
            cand = os.path.abspath(cand)
            if os.path.isfile(cand) and cand.lower().endswith(ext):
                return cand
            hit = _pick_template_in_dir(cand, ext)
            if hit:
                return hit

    # 用户自己的“文件模板”搜索目录：天然跟随版本，且默认槽位为空时仍然有效
    # （SW2018 的图纸模板槽位就是空的）。
    for folder in _pref_str(sw, _SW_TEMPLATE_SEARCH_FOLDERS).split(";"):
        hit = _pick_template_in_dir(
            os.path.expandvars(folder.strip().strip('"')), ext)
        if hit:
            return hit

    for folder in _installed_template_dirs(sw):
        hit = _pick_template_in_dir(folder, ext)
        if hit:
            return hit

    raise FileNotFoundError("找不到模板 *%s（默认模板设置与安装目录里都没有）" % ext)


def find_part_template(sw):
    """按用户默认模板设置查找零件模板，兜底按版本搜索安装目录。"""
    return find_template(sw, ".prtdot")


def find_drawing_template(sw):
    """按用户默认模板设置查找图纸模板，兜底按版本搜索安装目录。"""
    return find_template(sw, ".drwdot")


def new_part(sw, template=None):
    template = template or find_part_template(sw)
    try:
        sw.SetUserPreferenceToggle(_SW_ALWAYS_USE_DEFAULT_TEMPLATES, True)
    except Exception:
        pass
    model = sw.NewDocument(template, 0, 0, 0)
    if model is None:
        for _ in range(20):
            model = sw.ActiveDoc
            if model is not None:
                break
            time.sleep(0.25)
    if model is None:
        raise RuntimeError("新建零件失败：SW 未返回活动文档")
    return _early(model, "IModelDoc2")


def open_doc(sw, path, doc_type=1, read_only=False):
    """打开文档（1=swDocPART 2=swDocASSEMBLY 3=swDocDRAWING）；已打开则复用。"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    target = os.path.normcase(path)
    for doc in com_get(_dyn(sw), "GetDocuments") or []:
        try:
            if os.path.normcase(com_get(doc, "GetPathName") or "") == target:
                return _early(doc, "IModelDoc2")
        except Exception:
            continue
    errors, warnings = err_variants()
    model = _dyn(sw).OpenDoc6(path, doc_type, 1 if read_only else 0, "", errors, warnings)
    if model is None:
        raise RuntimeError(f"打开失败: {path} (err={errors.value} warn={warnings.value})")
    return _early(model, "IModelDoc2")


def save_as(model, path, sw=None):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if sw is not None:
        close_doc_by_path(sw, path)  # 目标文件若已在 SW 中打开，先关闭，避免 SaveAs err=1
    errors, warnings = err_variants()
    empty = VARIANT(pythoncom.VT_DISPATCH, None)
    # 早绑定包装对 VARIANT 参数转换不佳，SaveAs 走后期绑定
    dyn = win32com.client.Dispatch(model._oleobj_)
    ok = dyn.Extension.SaveAs(path, 0, 1, empty, errors, warnings)
    if not ok:
        raise RuntimeError(f"保存失败 err={errors.value} warn={warnings.value}")
    return path


def close_doc_by_path(sw, path):
    """关闭与 path 对应的已打开文档（比对文档路径，忽略大小写与斜杠）。"""
    target = os.path.normcase(os.path.abspath(path))
    try:
        docs = com_get(_dyn(sw), "GetDocuments")
    except Exception:
        return
    for doc in docs or []:
        try:
            doc_path = os.path.normcase(com_get(doc, "GetPathName") or "")
            title = com_get(doc, "GetTitle")
        except Exception:
            continue
        if doc_path and doc_path == target:
            _dyn(sw).CloseDoc(title)


def mass_properties(model):
    """返回 dict(volume_m3, mass_kg, density_kg_m3, surface_area_m2)。

    密度取自 SW 材料属性；未赋材料时 SW 默认 1000 kg/m3。
    """
    mp = model.Extension.CreateMassProperty()
    return {
        "volume_m3": float(mp.Volume),
        "mass_kg": float(mp.Mass),
        "density_kg_m3": float(mp.Density),
        "surface_area_m2": float(mp.SurfaceArea),
    }


def rebuild(model, top_only=False):
    """模型重建（True=仅顶层装配/零件，False=所有配置）。"""
    return bool(model.ForceRebuild3(top_only))


def select_by_id(model, name, sel_type, x=0, y=0, z=0, append=False, mark=0):
    return _dyn(model).Extension.SelectByID2(name, sel_type, x, y, z, append, mark,
                                             _empty_callout(), 0)


def select_edge_near(model, x, y, z):
    """按模型空间坐标选最近边线。"""
    model.ClearSelection2(True)
    return _dyn(model).Extension.SelectByID2("", "EDGE", x, y, z, False, 0,
                                             _empty_callout(), 0)


def clear_selection(model):
    """清空选择集。"""
    return model.ClearSelection2(True)


def model_title(model):
    try:
        return str(com_get(model, "GetTitle"))
    except Exception:
        return "unknown"


def model_path(model):
    try:
        return str(com_get(model, "GetPathName") or "")
    except Exception:
        return ""


def walk_features(model):
    """遍历顶层特征树（不含子特征），yield 早绑定 IFeature。"""
    feat = _early(model.FirstFeature(), "IFeature") if model.FirstFeature() is not None else None
    while feat is not None:
        yield feat
        nxt = feat.GetNextFeature()
        feat = _early(nxt, "IFeature") if nxt is not None else None


def feature_type(feat):
    try:
        return str(feat.GetTypeName2())
    except Exception:
        return ""


def feature_name(feat):
    try:
        return str(feat.Name)
    except Exception:
        return ""


def get_whats_wrong(model):
    """读取 What's Wrong 列表。SW 版本无该接口时返回 None（不致命）。"""
    try:
        ext = model.Extension
        n = int(ext.GetWhatsWrongCount())
    except Exception:
        return None
    items = []
    for i in range(1, n + 1):
        try:
            info = ext.GetWhatsWrongInfo(i)
            items.append({"index": i, "severity": info[0] if isinstance(info, tuple) else "",
                          "message": str(info[1] if isinstance(info, tuple) else info)})
        except Exception:
            try:
                items.append({"index": i, "message": str(ext.GetWhatsWrongInfo(i))})
            except Exception:
                items.append({"index": i, "message": f"<读取失败 {i}>"})
    return items


def feature_error_codes(feat):
    """读取特征错误/警告码。失败返回 (-1,-1)。"""
    errors, warnings = err_variants()
    try:
        dyn = _dyn(_early(feat, "IFeature"))
        dyn.GetErrorCode2(errors, warnings)
        return int(errors.value), int(warnings.value)
    except Exception:
        try:
            return int(feat.GetErrorCode2(errors, warnings)), int(warnings.value)
        except Exception:
            return -1, -1
