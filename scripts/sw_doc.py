"""sw_doc.py — 文档 / 特征树 / 尺寸 / 自定义属性 / 导出 / 视图截图

AI 闭环所需的"读"能力：先看清模型里有什么（特征、尺寸全名、属性），
改完能拿到截图自己看结果。长度单位：毫米；角度：度。
"""
import os
import tempfile
import time

import pythoncom
from win32com.client import VARIANT

import sw_core

_DOC_TYPES = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}
_DOC_TYPE_NAMES = {1: "part", 2: "assembly", 3: "drawing"}
# swStandardViews_e：ShowNamedView2("", id) 与界面语言无关
_VIEWS = {"front": 1, "back": 2, "left": 3, "right": 4, "top": 5, "bottom": 6,
          "isometric": 7, "trimetric": 8, "dimetric": 9}
_EXPORT_EXTS = {".step", ".stp", ".igs", ".iges", ".stl", ".x_t", ".x_b", ".sat",
                ".3mf", ".wrl", ".pdf", ".dxf", ".dwg", ".eprt", ".easm", ".edrw", ".3dxml"}


def doc_type_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in _DOC_TYPES:
        raise ValueError(f"不支持的 SolidWorks 文档扩展名 {ext!r}")
    return _DOC_TYPES[ext]


# ---------------------------------------------------------------------------
# 文档
# ---------------------------------------------------------------------------

def documents(sw):
    out = []
    active = None
    try:
        a = sw.ActiveDoc
        active = sw_core.model_title(a) if a is not None else None
    except Exception:
        pass
    for d in sw_core.com_get(sw_core._dyn(sw), "GetDocuments") or []:
        d = sw_core._early(d, "IModelDoc2")
        title = sw_core.model_title(d)
        rec = {"title": title, "path": sw_core.model_path(d) or None, "active": title == active}
        try:
            rec["type"] = _DOC_TYPE_NAMES.get(int(d.GetType()), "other")
        except Exception:
            pass
        try:
            rec["dirty"] = bool(d.GetSaveFlag())
        except Exception:
            pass
        try:
            rec["visible"] = bool(d.Visible)
        except Exception:
            pass
        out.append(rec)
    return out


def activate(sw, model):
    errors, _ = sw_core.err_variants()
    try:
        sw_core._dyn(sw).ActivateDoc3(sw_core.model_title(model), False, 0, errors)
    except Exception:
        sw_core._dyn(sw).ActivateDoc2(sw_core.model_title(model), False, errors)
    return model


def open_document(sw, path):
    model = sw_core.open_doc(sw, path, doc_type=doc_type_for(path))
    activate(sw, model)
    return model


def find_open(sw, title_or_path):
    """按标题或路径找已打开文档。"""
    key = os.path.normcase(str(title_or_path))
    for d in sw_core.com_get(sw_core._dyn(sw), "GetDocuments") or []:
        d = sw_core._early(d, "IModelDoc2")
        if sw_core.model_title(d) == title_or_path or \
                os.path.normcase(sw_core.model_path(d)) == key:
            return d
    raise RuntimeError(f"没有已打开的文档 {title_or_path!r}")


def save(sw, model, path=""):
    if path:
        return {"saved": sw_core.save_as(model, path, sw=sw)}
    errors, warnings = sw_core.err_variants()
    ok = sw_core._dyn(model).Save3(1, errors, warnings)  # swSaveAsOptions_Silent
    if not ok:
        raise RuntimeError(f"保存失败 err={errors.value} warn={warnings.value}"
                           "（新文档请提供 path）")
    return {"saved": sw_core.model_path(model)}


def close(sw, model, save_first=False):
    title = sw_core.model_title(model)
    if save_first:
        save(sw, model)
    sw.CloseDoc(title)
    return {"closed": title}


def export(sw, model, path):
    """按扩展名导出（STEP/IGES/STL/Parasolid/PDF/DXF/eDrawings...）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _EXPORT_EXTS:
        raise ValueError(f"不支持的导出格式 {ext}；可选 {sorted(_EXPORT_EXTS)}"
                         "（图片请用 view_capture）")
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    errors, warnings = sw_core.err_variants()
    ok = sw_core._dyn(model).Extension.SaveAs(path, 0, 1, VARIANT(pythoncom.VT_DISPATCH, None),
                                              errors, warnings)
    if not ok or not os.path.exists(path):
        raise RuntimeError(f"导出失败 {path} err={errors.value} warn={warnings.value}")
    return {"exported": path, "bytes": os.path.getsize(path)}


# ---------------------------------------------------------------------------
# 视图截图
# ---------------------------------------------------------------------------

def capture(sw, model, view="isometric", width=1200, height=900, out_path=""):
    """切到标准视角、缩放到合适、SaveBMP -> PNG。返回 (png_path, png_bytes)。"""
    from PIL import Image

    activate(sw, model)
    dyn = sw_core._dyn(model)
    if view and view != "current":
        if view not in _VIEWS:
            raise ValueError(f"view 必须是 {sorted(_VIEWS)} 或 current")
        try:
            dyn.ShowNamedView2("", _VIEWS[view])
        except Exception:
            dyn.ShowNamedView2("*" + view.capitalize(), -1)
    try:
        dyn.ViewZoomtofit2()
    except Exception:
        pass
    time.sleep(0.4)
    bmp = os.path.join(tempfile.mkdtemp(prefix="swcap_"), "view.bmp")
    if not dyn.SaveBMP(bmp, int(width), int(height)):
        raise RuntimeError("SaveBMP 失败（文档窗口不可见或已最小化？）")
    png = out_path or bmp[:-4] + ".png"
    im = Image.open(bmp).convert("RGB")
    im.save(png, "PNG")
    try:
        os.remove(bmp)
    except OSError:
        pass
    with open(png, "rb") as fh:
        return png, fh.read()


# ---------------------------------------------------------------------------
# 特征树
# ---------------------------------------------------------------------------

def _sub_features(feat):
    try:
        sub = feat.GetFirstSubFeature()
    except Exception:
        return
    while sub is not None:
        sub = sw_core._early(sub, "IFeature")
        yield sub
        try:
            sub = sub.GetNextSubFeature()
        except Exception:
            return


def _feat_rec(feat, depth=0):
    err, warn = sw_core.feature_error_codes(feat)
    rec = {"name": sw_core.feature_name(feat), "type": sw_core.feature_type(feat)}
    if depth:
        rec["parent_depth"] = depth
    try:
        rec["suppressed"] = bool(feat.IsSuppressed())
    except Exception:
        pass
    if err not in (0, -1):
        rec["error_code"] = err
    if warn not in (0, -1):
        rec["warning_code"] = warn
    return rec


# 基础/隐藏特征，默认不列出，减少噪音
_NOISE_TYPES = {"CommentsFolder", "FavoriteFolder", "HistoryFolder", "SelectionSetFolder",
                "SensorFolder", "DocsFolder", "DetailCabinet", "SurfaceBodyFolder",
                "SolidBodyFolder", "EnvFolder", "InkMarkupFolder", "EqnFolder",
                "MaterialFolder", "MBD3DViewFolder", "BlockFolder", "LiveSectionFolder",
                "DisplayStateFolder", "ProfileCenterMarkFolder", "MateReferenceGroupFolder"}


def features(model, include_sub=True, include_hidden=False):
    out = []
    for feat in sw_core.walk_features(model):
        rec = _feat_rec(feat)
        if not include_hidden and rec["type"] in _NOISE_TYPES:
            continue
        if include_sub:
            subs = [_feat_rec(s, 1) for s in _sub_features(feat)]
            if subs:
                rec["children"] = subs
        out.append(rec)
    return out


def _find_feature(model, name):
    feat = sw_core._early(model, "IModelDoc2").FeatureByName(str(name))
    if feat is None:
        raise RuntimeError(f"没有名为 {name!r} 的特征")
    return sw_core._early(feat, "IFeature")


def _feature_names(model):
    names = set()
    for f in sw_core.walk_features(model):
        names.add(sw_core.feature_name(f))
        names.update(sw_core.feature_name(s) for s in _sub_features(f))
    return names


def suppress_feature(model, name, suppress=True):
    feat = _find_feature(model, name)
    state = 0 if suppress else 1  # swFeatureSuppressionAction_e
    ok = None
    for args in ((state, 2, None), (state, 1, None), (state,)):  # 2=所有配置
        try:
            ok = feat.SetSuppression2(*args)
            break
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise
    sw_core.rebuild(model)
    return {"feature": name, "suppressed": bool(feat.IsSuppressed()), "ok": bool(ok)}


def delete_feature(model, name, keep_absorbed=False):
    """删除特征（默认连同被吸收的草图）。返回实际被删除的特征名清单。"""
    before = _feature_names(model)
    feat = _find_feature(model, name)
    model.ClearSelection2(True)
    if not feat.Select2(False, 0):
        raise RuntimeError(f"选择特征 {name} 失败")
    opts = 0 if keep_absorbed else 1  # swDelete_Absorbed
    if not sw_core._dyn(model).Extension.DeleteSelection2(opts):
        raise RuntimeError(f"删除 {name} 失败")
    sw_core.rebuild(model)
    return {"deleted": sorted(before - _feature_names(model))}


def undo(model, count=1):
    before = len(features(model, include_sub=False, include_hidden=True))
    sw_core._dyn(model).EditUndo2(int(count))
    after = len(features(model, include_sub=False, include_hidden=True))
    return {"undone": int(count), "feature_count_before": before, "feature_count_after": after}


# ---------------------------------------------------------------------------
# 尺寸
# ---------------------------------------------------------------------------

def _display_dims(feat):
    try:
        dd = feat.GetFirstDisplayDimension()
    except Exception:
        return
    while dd is not None:
        yield sw_core._early(dd, "IDisplayDimension")
        try:
            dd = feat.GetNextDisplayDimension(dd)
        except Exception:
            return


def _is_angle(dim):
    try:
        return int(dim.GetType()) == 2  # swDimensionParamType_e: 2=DoubleAngular
    except Exception:
        return False


def _dim_rec(dd):
    dim = sw_core._early(dd.GetDimension2(0), "IDimension")
    v = float(dim.SystemValue)
    rec = {"name": str(dim.FullName)}
    if _is_angle(dim):
        import math
        rec.update(value=round(math.degrees(v), 6), unit="deg")
    else:
        rec.update(value=round(v * 1000.0, 6), unit="mm")
    try:
        rec["driven"] = bool(dim.DrivenState == 1)  # swDimensionDriven
    except Exception:
        pass
    return rec


def dimensions(model, feature=None):
    """列出尺寸全名（如 D1@草图1）与当前值，set_dimension 直接用这个全名。"""
    feats = [_find_feature(model, feature)] if feature else list(sw_core.walk_features(model))
    out = []
    for f in feats:
        for target in [f] + list(_sub_features(f)):
            for dd in _display_dims(target):
                try:
                    out.append(_dim_rec(dd))
                except Exception:
                    continue
    seen, uniq = set(), []
    for r in out:
        if r["name"] not in seen:
            seen.add(r["name"])
            uniq.append(r)
    return uniq


def set_dimension(model, name, value):
    """按全名改尺寸（长度 mm / 角度 deg，按尺寸类型自动换算）并重建。"""
    dim = model.Parameter(str(name))
    if dim is None:
        raise RuntimeError(f"没有尺寸 {name!r}（先用 dimension_list 查看全名）")
    dim = sw_core._early(dim, "IDimension")
    import math
    old = float(dim.SystemValue)
    is_angle = _is_angle(dim)
    new = math.radians(float(value)) if is_angle else float(value) / 1000.0
    ret = None
    try:
        ret = dim.SetSystemValue3(new, 2, None)  # swSetValue_InAllConfigurations
    except Exception:
        sw_core.com_set(dim, "SystemValue", new)
    model.EditRebuild3()
    cur = float(dim.SystemValue)
    scale = (lambda x: math.degrees(x)) if is_angle else (lambda x: x * 1000.0)
    return {"name": name, "old": round(scale(old), 6), "new": round(scale(cur), 6),
            "unit": "deg" if is_angle else "mm", "set_return": ret}


# ---------------------------------------------------------------------------
# 自定义属性
# ---------------------------------------------------------------------------

def _cpm(model, config=""):
    return sw_core._early(model.Extension.CustomPropertyManager(str(config)),
                          "ICustomPropertyManager")


def custom_properties(model, config=""):
    cpm = _cpm(model, config)
    out = {}
    for name in cpm.GetNames() or []:
        try:
            r = cpm.Get4(name, False)
            out[name] = r[1] if isinstance(r, tuple) and len(r) > 1 else r
        except Exception:
            try:
                out[name] = cpm.Get(name)
            except Exception:
                out[name] = None
    return out


def set_custom_properties(model, props, config=""):
    cpm = _cpm(model, config)
    done = {}
    for k, v in (props or {}).items():
        # Add3(name, swCustomInfoText=30, value, swCustomPropertyReplaceValue=2)
        done[k] = int(cpm.Add3(str(k), 30, str(v), 2))
    return {"set": done, "properties": custom_properties(model, config)}
