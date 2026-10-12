"""sw_part_dsl.py — 通用零件建模 spec DSL（补全清单 7.1/7.3）

JSON spec → SolidWorks 零件。纯校验/规范化部分不依赖 pywin32，可在 Linux 单测。

spec v1 示例：
{
  "units": "mm",
  "planes": [{"name": "P1", "type": "offset", "base": "front", "distance_mm": 10}],
  "sketches": [
    {"name": "sk1", "plane": "front",
     "entities": [
        {"type": "corner_rectangle", "x1": 0, "y1": 0, "x2": 20, "y2": 10}
     ],
     "dims": [{"kind": "linear", "p1": [0, 0], "p2": [20, 0], "horizontal": true,
               "text": [10, -2]}],
     "relations": []}
  ],
  "features": [
    {"op": "extrude_boss", "sketch": "sk1", "depth_mm": 5}
  ],
  "names": [{"name": "TOP", "ref": {"spec": {"kind": "plane", "normal": [0, 0, 1],
                                              "directional": true}}}],
  "checks": {"expect_volume_mm3": 1000.0},
  "save": "out/part.SLDPRT"
}

设计约定：
  - 所有 *_mm 字段为毫米，执行层转米；
  - sketch 名称映射：创建后捕获 SW 实际草图名，后续 feature 用 spec 中的逻辑名；
  - 特征 op 与 sw_features / sw_advanced 函数一一对应（ops_available() 可查询）；
  - names：特征完成后给面/边命名（ref 同 sw_topo.resolve），供装配按
    {"component":..,"face":name} 稳定引用。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_SKETCH_ENTITY_PARAMS = {
    "line": ["x1", "y1", "x2", "y2"],
    "centerline": ["x1", "y1", "x2", "y2"],
    "arc": ["cx", "cy", "x1", "y1", "x2", "y2", "direction"],
    "arc3pt": ["x1", "y1", "x2", "y2", "x3", "y3"],
    "circle": ["cx", "cy", "r"],
    "circle3pt": ["x1", "y1", "x2", "y2", "x3", "y3"],
    "ellipse": ["cx", "cy", "rx", "ry", "angle_deg"],
    "spline": ["points"],
    "corner_rectangle": ["x1", "y1", "x2", "y2"],
    "center_rectangle": ["cx", "cy", "x2", "y2"],
    "three_point_corner_rectangle": ["x1", "y1", "x2", "y2", "x3", "y3"],
    "three_point_center_rectangle": ["cx", "cy", "x1", "y1", "x2", "y2"],
    "parallelogram": ["x1", "y1", "x2", "y2", "x3", "y3"],
    "polygon": ["cx", "cy", "n", "radius", "inscribed"],
    "slot": ["cx", "cy", "length", "width", "angle_deg"],
    "point": ["x", "y"],
    "text": ["text", "x", "y", "height_m", "angle_deg"],
}

_STANDARD_PLANES = ("front", "top", "right")

# op -> (模块, 函数, DSL 毫米字段 → 包装函数参数 的映射)
# 约定：spec 里用 *_mm；包装函数用 *_m；此处把 *_mm 值 /1000 后以 *_m 名传入。
_FEATURE_OPS = {
    "extrude_boss": ("sw_features", "extrude_boss", {"depth_mm": "depth_m"}),
    "extrude_cut": ("sw_features", "extrude_cut", {"depth_mm": "depth_m"}),
    "revolve_boss": ("sw_features", "revolve_boss", {}),
    "revolve_cut": ("sw_features", "revolve_cut", {}),
    "sweep_boss": ("sw_features", "sweep_boss", {}),
    "sweep_cut": ("sw_features", "sweep_cut", {}),
    "loft_boss": ("sw_features", "loft_boss", {}),
    "loft_cut": ("sw_features", "loft_cut", {}),
    "boundary_boss": ("sw_features", "boundary_boss", {}),
    "boundary_cut": ("sw_features", "boundary_cut", {}),
    "thicken": ("sw_features", "thicken", {"thickness_mm": "thickness_m"}),
    "fillet": ("sw_features", "fillet", {"radius_mm": "radius_m"}),
    "chamfer": ("sw_features", "chamfer", {"distance_mm": "distance_m"}),
    "shell": ("sw_features", "shell", {"thickness_mm": "thickness_m"}),
    "draft": ("sw_features", "draft", {}),
    "rib": ("sw_features", "rib", {"thickness_mm": "thickness_m"}),
    "dome": ("sw_features", "dome", {"height_mm": "height_m"}),
    "wrap": ("sw_features", "wrap", {"depth_mm": "depth_m"}),
    "simple_hole": ("sw_features", "simple_hole",
                    {"diameter_mm": "diameter_m", "depth_mm": "depth_m"}),
    "hole_wizard": ("sw_features", "hole_wizard", {}),
    "move_face": ("sw_features", "move_face", {"dx_mm": "dx_m", "dy_mm": "dy_m",
                                               "dz_mm": "dz_m", "distance_mm": "distance_m"}),
    "delete_face": ("sw_features", "delete_face", {}),
    "scale_feature": ("sw_features", "scale_feature", {}),
    "flex": ("sw_features", "flex", {}),
    "deform": ("sw_features", "deform", {}),
    "linear_pattern": ("sw_features", "linear_pattern",
                       {"d1_spacing_mm": "d1_spacing_m", "d2_spacing_mm": "d2_spacing_m"}),
    "circular_pattern": ("sw_features", "circular_pattern", {}),
    "mirror_feature": ("sw_features", "mirror_feature", {}),
    "sketch_driven_pattern": ("sw_features", "sketch_driven_pattern", {}),
    "curve_driven_pattern": ("sw_features", "curve_driven_pattern",
                             {"spacing_mm": "spacing_m"}),
    "table_driven_pattern": ("sw_features", "table_driven_pattern", {}),
    "fill_pattern": ("sw_features", "fill_pattern", {"spacing_mm": "spacing_m"}),
    "variable_pattern": ("sw_features", "variable_pattern", {}),
    "combine": ("sw_features", "combine", {}),
    "split": ("sw_features", "split", {}),
    "indent": ("sw_features", "indent", {"depth_mm": "depth_m"}),
    "cavity": ("sw_features", "cavity", {"depth_mm": "depth_m"}),
    "move_copy_body": ("sw_features", "move_copy_body",
                       {"dx_mm": "dx_m", "dy_mm": "dy_m", "dz_mm": "dz_m"}),
    "set_material": ("sw_features", "set_material", {}),
    "custom_properties": ("sw_features", "custom_properties", {}),
    # 配置/方程式/设计表（sw_config，补全清单 5.1-5.3）
    "add_configuration": ("sw_config", "add_configuration", {}),
    "activate_configuration": ("sw_config", "show_configuration", {}),
    "delete_configuration": ("sw_config", "delete_configuration", {}),
    "list_configurations": ("sw_config", "list_configurations", {}),
    "add_equation": ("sw_config", "add_equation", {}),
    "add_global_variable": ("sw_config", "add_global_variable", {}),
    "rebuild_equations": ("sw_config", "rebuild_equations", {}),
    "insert_design_table": ("sw_config", "insert_design_table", {}),
    # 参考几何/曲线/曲面（sw_advanced，函数已接受 *_mm 的参数原样透传）
    "ref_plane": ("sw_advanced", "insert_ref_plane", {}),
    "ref_axis": ("sw_advanced", "insert_axis", {}),
    "ref_point": ("sw_advanced", "insert_reference_point", {}),
    "coordinate_system": ("sw_advanced", "insert_coordinate_system", {}),
    "helix": ("sw_advanced", "helix", {}),
    "projected_curve": ("sw_advanced", "projected_curve", {}),
    "composite_curve": ("sw_advanced", "composite_curve", {}),
    "split_line": ("sw_advanced", "split_line", {}),
    "curve_through_points": ("sw_advanced", "curve_through_points", {}),
    "curve_from_xyz_file": ("sw_advanced", "curve_from_xyz_file", {}),
    "extruded_surface": ("sw_advanced", "extruded_surface", {"depth_mm": "depth_m"}),
    "revolved_surface": ("sw_advanced", "revolved_surface", {}),
    "lofted_surface": ("sw_advanced", "lofted_surface", {}),
    "boundary_surface": ("sw_advanced", "boundary_surface", {}),
    "planar_surface": ("sw_advanced", "planar_surface", {}),
    "fill_surface": ("sw_advanced", "fill_surface", {}),
    "offset_surface": ("sw_advanced", "offset_surface", {}),
    "extend_surface": ("sw_advanced", "extend_surface", {"distance_mm": "distance_m"}),
    "trim_surface": ("sw_advanced", "trim_surface", {}),
    "untrim_surface": ("sw_advanced", "untrim_surface", {}),
    "knit_surface": ("sw_advanced", "knit_surface", {}),
    "cut_with_surface": ("sw_advanced", "cut_with_surface", {}),

    "replace_face": ("sw_advanced", "replace_face", {}),
    # 装饰螺纹 / 特征树 / 外观（SW2018 本机扩展）
    "cosmetic_thread": ("sw_features", "cosmetic_thread", {"diameter_mm": "diameter_m"}),
    "rollback_feature": ("sw_features", "rollback_feature", {}),
    "rollforward_feature": ("sw_features", "rollforward_feature", {}),
    "reorder_feature": ("sw_features", "reorder_feature", {}),
    "rename_feature": ("sw_features", "rename_feature", {}),
    "create_feature_folder": ("sw_features", "create_feature_folder", {}),
    "set_appearance": ("sw_features", "set_appearance", {}),
    "set_scene": ("sw_features", "set_scene", {}),
    # DimXpert/MBD 尺寸标注
    "dimxpert_counts": ("sw_annotate", "dimxpert_counts", {}),
    "dimxpert_add_dimension": ("sw_annotate", "dimxpert_add_dimension", {}),
    "dimxpert_auto_dimension": ("sw_annotate", "dimxpert_auto_dimension", {}),
    "dimxpert_delete_tolerances": ("sw_annotate", "dimxpert_delete_tolerances", {}),
}

_ALLOWED_KEYS = {"units", "name", "planes", "sketches", "features", "names", "checks",
                 "save"}


class SpecError(ValueError):
    """spec 结构/参数错误。"""


def ops_available():
    return sorted(_FEATURE_OPS.keys())


def validate_spec(spec):
    """纯 Python 校验，返回 (normalized_spec, errors)。不连 SW。"""
    if not isinstance(spec, dict):
        raise SpecError("spec 必须是 dict")
    errors = []
    for k in spec:
        if k not in _ALLOWED_KEYS:
            errors.append(f"未知字段: {k}（允许 {sorted(_ALLOWED_KEYS)}）")
    units = str(spec.get("units", "mm")).lower()
    if units != "mm":
        errors.append(f"当前仅支持 units=mm，收到 {units}")
    planes = spec.get("planes") or []
    sketches = spec.get("sketches") or []
    features = spec.get("features") or []
    for i, p in enumerate(planes):
        if not isinstance(p, dict) or not p.get("name"):
            errors.append(f"planes[{i}] 缺少 name")
    plane_names = {p.get("name") for p in planes}
    sketch_names = []
    for i, s in enumerate(sketches):
        if not isinstance(s, dict):
            errors.append(f"sketches[{i}] 必须是 dict")
            continue
        name = s.get("name")
        if not name:
            errors.append(f"sketches[{i}] 缺少 name")
        sketch_names.append(name)
        plane = s.get("plane")
        if plane not in _STANDARD_PLANES and plane not in plane_names:
            errors.append(f"sketches[{i}] 的 plane={plane!r} 未在 planes 中定义")
        ents = s.get("entities") or []
        if not isinstance(ents, list) or not ents:
            errors.append(f"sketches[{i}] entities 必须是非空列表")
        for j, e in enumerate(ents or []):
            etype = e.get("type")
            if etype not in _SKETCH_ENTITY_PARAMS:
                errors.append(f"sketches[{i}].entities[{j}] 未知 type: {etype}")
            else:
                missing = [p for p in _SKETCH_ENTITY_PARAMS[etype] if p not in e]
                if missing:
                    errors.append(f"sketches[{i}].entities[{j}] ({etype}) 缺参数: {missing}")
    for i, f in enumerate(features):
        if not isinstance(f, dict):
            errors.append(f"features[{i}] 必须是 dict")
            continue
        op = f.get("op")
        if op not in _FEATURE_OPS:
            errors.append(f"features[{i}] 未知 op: {op}（可用 ops_available() 查询）")
        sk = f.get("sketch")
        if sk and sketch_names and sk not in sketch_names:
            errors.append(f"features[{i}] sketch={sk!r} 未在 sketches 中定义")
    seen_names = set()
    for i, n in enumerate(spec.get("names") or []):
        if not isinstance(n, dict) or not n.get("name") or not isinstance(n.get("ref"), dict):
            errors.append(f"names[{i}] 需要 {{name, ref}}，ref 为 spec/ray/index/persist_id 之一")
            continue
        if n["name"] in seen_names:
            errors.append(f"names[{i}] 名字重复: {n['name']}")
        seen_names.add(n["name"])
    checks = spec.get("checks") or {}
    if "expect_volume_mm3" in checks:
        try:
            float(checks["expect_volume_mm3"])
        except Exception:
            errors.append("checks.expect_volume_mm3 必须是数值")
    if "save" in spec and not str(spec["save"]).lower().endswith(".sldprt"):
        errors.append("save 必须为 .SLDPRT 路径")
    return spec, errors


def dry_run(spec):
    """不连 SW 的预检：校验 + 操作清单 + 预计特征数。"""
    normalized, errors = validate_spec(spec)
    ops = [{"index": i, "op": f.get("op"), "module": _FEATURE_OPS[f["op"]][0],
            "function": _FEATURE_OPS[f["op"]][1]}
           for i, f in enumerate(normalized.get("features") or [])]
    return {"valid": not errors, "errors": errors,
            "plane_count": len(normalized.get("planes") or []),
            "sketch_count": len(normalized.get("sketches") or []),
            "feature_ops": ops,
            "hint": "签名类差异以 SW2018 实机集成为准：scripts/tests/integration_sw2018.py"}


# ---------- 执行层（仅在 Windows + pywin32 环境导入） ----------

def _mm(v):
    import sw_core
    return sw_core.mm(v)


def _load(mod_name):
    import importlib
    return importlib.import_module(mod_name)


def _draw_entity(sketch_mod, model, e):
    fn = getattr(sketch_mod, e["type"])
    args = []
    for p in _SKETCH_ENTITY_PARAMS[e["type"]]:
        val = e.get(p)
        if p == "points":
            args.append([(_mm(x), _mm(y)) for x, y in val])
        elif p == "text":
            args.append(str(val))
        elif p == "height_m":
            args.append(_mm(val))
        elif p in ("n", "inscribed", "direction", "angle_deg"):
            args.append(val if val is not None else (1 if p == "direction" else 0))
        else:
            args.append(_mm(val))
    seg = fn(model, *args)
    if e.get("construction"):
        sketch_mod.set_construction(seg, True)
    return seg


def _apply_sketch_extra(sketch_mod, model, s):
    for d in (s.get("dims") or []):
        kind = d.get("kind")
        if kind in ("linear", "horizontal", "vertical"):
            horizontal = kind != "vertical"
            sketch_mod.add_linear_dimension(model, _mm(d["p1"][0]), _mm(d["p1"][1]),
                                            _mm(d["p2"][0]), _mm(d["p2"][1]),
                                            horizontal=horizontal)
        elif kind == "radial":
            sketch_mod.add_radial_dimension(model,
                                            [_mm(d["arc_center"][0]), _mm(d["arc_center"][1])],
                                            [_mm(d["arc_point"][0]), _mm(d["arc_point"][1])],
                                            _mm(d["text"][0]), _mm(d["text"][1]))
        elif kind == "diameter":
            sketch_mod.add_diameter_dimension(model,
                                              [_mm(d["arc_center"][0]), _mm(d["arc_center"][1])],
                                              [_mm(d["arc_point"][0]), _mm(d["arc_point"][1])],
                                              _mm(d["text"][0]), _mm(d["text"][1]))
        elif kind == "angular":
            sketch_mod.add_angular_dimension(model,
                                             [_mm(d["p1"][0]), _mm(d["p1"][1])],
                                             [_mm(d["p2"][0]), _mm(d["p2"][1])],
                                             [_mm(d["p3"][0]), _mm(d["p3"][1])],
                                             [_mm(d["p4"][0]), _mm(d["p4"][1])],
                                             _mm(d["text"][0]), _mm(d["text"][1]))
        else:
            raise SpecError(f"未知尺寸类型: {kind}")
    for r in (s.get("relations") or []):
        sketch_mod.add_relation(model, r["type"], r.get("targets", []),
                                add_to_db=bool(r.get("add_to_db", True)))


def _capture_sketch_name(model, wanted, sketch_mod):
    try:
        sk = sketch_mod.active_sketch(model)
        name = sk.Name
        if name:
            return str(name)
    except Exception:
        pass
    try:
        feat = sketch_mod.last_sketch_feature(model)
        return sw_core_name(feat)
    except Exception:
        pass
    return wanted


def sw_core_name(feat):
    import sw_core
    return sw_core.feature_name(feat)


def _apply_feature(mod, model, f, sketch_names):
    fn = getattr(mod, f["op"])
    kwargs = {}
    mapping = _FEATURE_OPS[f["op"]][2]
    for k, v in f.items():
        if k in ("op", "sketch", "sketches", "profile_sketches"):
            continue
        target = mapping.get(k, k)
        kwargs[target] = _mm(v) if k in mapping else v
    if f.get("sketch") and f["sketch"] in sketch_names:
        kwargs["sketch"] = sketch_names[f["sketch"]]
    if f.get("sketches"):
        kwargs["sketches"] = [sketch_names.get(x, x) for x in f["sketches"]]
    if f.get("profile_sketches"):
        kwargs["profile_sketches"] = [sketch_names.get(x, x) for x in f["profile_sketches"]]
    # 其它 *_sketch / *_sketches 逻辑名 → SW 实际草图名（如 helix 的 circle_sketch）
    for k, v in list(kwargs.items()):
        if k.endswith("sketches") and isinstance(v, list):
            kwargs[k] = [sketch_names.get(x, x) for x in v]
        elif k.endswith("sketch") and isinstance(v, str) and v in sketch_names:
            kwargs[k] = sketch_names[v]
    ret = fn(model, **kwargs)
    return ret


def build_part(spec, out_path=None, sw=None, do_checks=True):
    """按 spec 建零件并保存。返回报告 dict。"""
    import sw_core
    import sw_sketch
    import sw_advanced
    import sw_check

    normalized, errors = validate_spec(spec)
    if errors:
        raise SpecError("spec 校验失败: " + "；".join(errors))

    own_sw = sw is None
    if own_sw:
        sw = sw_core.connect()
    model = sw_core.new_part(sw)
    report = {"steps": []}
    sketch_names = {}

    # 1. 参考几何（plane）
    plane_names = {"front": "front", "top": "top", "right": "right"}
    for p in normalized.get("planes") or []:
        feat, name = sw_advanced.insert_ref_plane(
            model, plane_type=p.get("type", "offset"),
            base_spec=p.get("base"), distance_mm=p.get("distance_mm", 0),
            angle_deg=p.get("angle_deg", 0), point_specs=p.get("point_specs"))
        plane_names[p["name"]] = name
        report["steps"].append(f"plane:{p['name']}->{name}")

    # 2. 草图
    for s in normalized.get("sketches") or []:
        plane = s.get("plane", "front")
        target = plane_names.get(plane, plane)
        if target in _STANDARD_PLANES or target == plane:
            sw_sketch.start_sketch(model, target)
        else:
            sw_sketch.start_sketch(model, {"name": target})
        for e in (s.get("entities") or []):
            _draw_entity(sw_sketch, model, e)
        _apply_sketch_extra(sw_sketch, model, s)
        sw_sketch.end_sketch(model)
        real = _capture_sketch_name(model, s["name"], sw_sketch)
        sketch_names[s["name"]] = real
        report["steps"].append(f"sketch:{s['name']}->{real}")

    # 3. 特征
    for i, f in enumerate(normalized.get("features") or []):
        mod_name = _FEATURE_OPS[f["op"]][0]
        mod = _load(mod_name)
        feat = _apply_feature(mod, model, f, sketch_names)
        report["steps"].append(f"feature[{i}]:{f['op']}->{getattr(feat, 'Name', feat)}")

    # 4. 实体命名（装配稳定引用）
    if normalized.get("names"):
        import sw_topo
        report["names"] = {}
        for n in normalized["names"]:
            ent, kind = sw_topo.resolve(model, n["ref"])
            sw_topo.name_entity(model, ent, n["name"])
            report["names"][n["name"]] = kind
        report["steps"].append(f"names:{sorted(report['names'])}")

    # 5. 校验与保存
    if do_checks:
        mp = sw_core.mass_properties(model)
        report["volume_mm3_sw"] = round(mp["volume_m3"] * 1e9, 4)
        report["mass_kg"] = round(mp["mass_kg"], 4)
        expect = (normalized.get("checks") or {}).get("expect_volume_mm3")
        if expect is not None:
            dev = abs(report["volume_mm3_sw"] - float(expect)) / abs(float(expect)) * 100
            report["volume_deviation_pct"] = round(dev, 4)
        report["deep_check"] = sw_check.deep_check(model)

    if out_path or normalized.get("save"):
        path = out_path or normalized["save"]
        report["saved"] = sw_core.save_as(model, path, sw=sw if own_sw else None)
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="通用零件 spec 建模")
    ap.add_argument("--spec", required=True, help="spec JSON 文件或 JSON 字符串")
    ap.add_argument("--out", default=None, help="输出 .SLDPRT")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    raw = args.spec
    if os.path.isfile(raw):
        with open(raw, encoding="utf-8") as fh:
            spec = json.load(fh)
    else:
        spec = json.loads(raw)
    if args.dry_run:
        print(json.dumps(dry_run(spec), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(build_part(spec, args.out), ensure_ascii=False, indent=2))
