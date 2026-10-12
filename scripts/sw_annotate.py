# -*- coding: utf-8 -*-
"""sw_annotate.py — 零件级尺寸标注（DimXpert/MBD 基础能力）。

SW2018 实测：
  - model.Extension.DimXpertManager(ConfigName, CreateSchema=True)
  - IDimXpertPart.InsertSizeDimension(GetDimOption)
  - IDimXpertPart.InsertLocationDimension(GetDimOption)
  - IDimXpertPart.InsertBasicDimension(GetDimOption)
以上方法在选中目标面后可直接创建 DimXpert 尺寸/注释。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_core
import sw_sel


def _dimxpert_part(model, config_name="默认", create_schema=True):
    """返回 (IDimXpertManager, IDimXpertPart)。"""
    cfg = str(config_name)
    try:
        dm = model.Extension.DimXpertManager(cfg, bool(create_schema))
    except Exception as exc:
        raise RuntimeError(f"DimXpertManager({cfg!r}) 失败: {exc}") from exc
    if dm is None:
        raise RuntimeError("DimXpertManager 返回 None（请先激活零件配置）")
    try:
        part = dm.DimXpertPart
    except Exception as exc:
        raise RuntimeError(f"读取 DimXpertPart 失败: {exc}") from exc
    if part is None:
        raise RuntimeError("DimXpertPart 为 None：需要 create_schema=True 创建 DimXpert schema")
    return dm, part


def dimxpert_counts(model, config_name="默认"):
    """返回 {feature_count, annotation_count}。"""
    _, part = _dimxpert_part(model, config_name)
    def _val(obj, name):
        v = getattr(obj, name, 0)
        return int(v) if v is not None else 0
    return {"feature_count": _val(part, "GetFeatureCount"),
            "annotation_count": _val(part, "GetAnnotationCount")}


def dimxpert_add_dimension(model, dim_type="size", face_spec=None,
                           config_name="默认"):
    """创建 DimXpert 尺寸。dim_type ∈ size / location / basic。

    face_spec: sw_sel 面 spec，例如
        {"kind":"cylinder","radius_mm":17.5,"axis":[0,1,0]}
    不传 face_spec 时使用当前选择。
    """
    desc = f"dimxpert_add_dimension(type={dim_type})"
    if face_spec is not None:
        sw_core.clear_selection(model)
        sw_sel.select_face(model, face_spec, mark=0)
    _, part = _dimxpert_part(model, config_name)
    opt = getattr(part, "GetDimOption", None)
    if opt is None:
        raise RuntimeError(f"{desc}: GetDimOption 不可用")
    method = {"size": "InsertSizeDimension",
              "location": "InsertLocationDimension",
              "basic": "InsertBasicDimension"}.get(str(dim_type).lower())
    if not method:
        raise RuntimeError(f"{desc}: dim_type 必须是 size/location/basic")
    try:
        ret = getattr(part, method)(opt)
    except Exception as exc:
        raise RuntimeError(f"{desc}: {method} 失败: {exc}") from exc
    counts = dimxpert_counts(model, config_name)
    return {"op": method, "returned": bool(ret), **counts}


def dimxpert_auto_dimension(model, config_name="默认"):
    """自动尺寸方案：使用 DimXpert 默认 AutoDimensionScheme。"""
    _, part = _dimxpert_part(model, config_name)
    opt = getattr(part, "GetAutoDimSchemeOption", None)
    if opt is None:
        raise RuntimeError("dimxpert_auto_dimension: GetAutoDimSchemeOption 不可用")
    try:
        ret = part.AutoDimensionScheme(opt)
    except Exception as exc:
        raise RuntimeError(f"dimxpert_auto_dimension: {exc}") from exc
    return {"returned": bool(ret), **dimxpert_counts(model, config_name)}


def dimxpert_delete_tolerances(model, config_name="默认"):
    """删除当前 DimXpert 公差。"""
    _, part = _dimxpert_part(model, config_name)
    try:
        ret = part.DeleteAllTolerances()
    except Exception as exc:
        raise RuntimeError(f"dimxpert_delete_tolerances: {exc}") from exc
    return {"returned": bool(ret), **dimxpert_counts(model, config_name)}


PUBLIC_API = [
    "dimxpert_counts",
    "dimxpert_add_dimension",
    "dimxpert_auto_dimension",
    "dimxpert_delete_tolerances",
]
