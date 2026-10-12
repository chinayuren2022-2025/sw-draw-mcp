"""sw_sketch_check.py — 通用零件草图约束完整性检查（与零件类型无关）

对任意 .SLDPRT：
  1. 遍历特征树，找出所有草图特征（ProfileFeature）
  2. 逐草图读取 GetConstrainedStatus（欠定义/完全定义/过定义/无解）
  3. 统计图元数、显示尺寸数、几何关系数，用于定位"缺约束"的严重程度
  4. 输出简短明确的中文提醒 + JSON 报告（供 LLM/harness 消费）

CLI：
  python sw_sketch_check.py                 # 检查当前活动零件
  python sw_sketch_check.py --file a.SLDPRT # 打开并检查指定零件
  python sw_sketch_check.py --json          # 只输出 JSON
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sw_core

# swConstrainedStatus_e（swconst.tlb v26 官方值，已从类型库常量核对）
_STATUS_TEXT = {
    1: "约束状态未知",
    2: "欠定义",
    3: "完全定义",
    4: "过定义",
    5: "无解",
    6: "无效解",
    7: "自动求解关闭",
}
_STATUS_EN = {1: "unknown", 2: "under-constrained", 3: "fully-constrained",
              4: "over-constrained", 5: "no-solution", 6: "invalid-solution",
              7: "autosolve-off"}
_BAD_CODES = (2, 4, 5, 6, 7)  # 需要提醒用户的状态


def iter_features(model):
    feat = model.FirstFeature()
    while feat is not None:
        feat = sw_core._early(feat, "IFeature")
        yield feat
        feat = feat.GetNextFeature()


def is_sketch_feature(feat):
    try:
        return feat.GetTypeName2() == "ProfileFeature"
    except Exception:
        return False


def sketch_report(sketch_feat):
    """单个草图特征 → 检查记录 dict。"""
    sk = sw_core._early(sketch_feat.GetSpecificFeature2(), "ISketch")
    name = sketch_feat.Name
    rec = {"sketch": name, "feature_type": "sketch"}
    if sk is None:
        rec.update(status="unknown", note="无法取得 ISketch 对象")
        return rec

    status_code = int(sk.GetConstrainedStatus())
    rec["status_code"] = status_code
    rec["status"] = _STATUS_TEXT.get(status_code, f"未知({status_code})")
    rec["status_en"] = _STATUS_EN.get(status_code, "unknown")

    segs = sk.GetSketchSegments()
    rec["segment_count"] = len(segs) if segs else 0

    # 显示尺寸数：IFeature.GetFirstDisplayDimension 链式遍历
    # （EnumDisplayDimensions 在 v26 是只写属性，读会报错）
    dim_count = 0
    try:
        dd = sketch_feat.GetFirstDisplayDimension()
        while dd is not None:
            dim_count += 1
            dd = sketch_feat.GetNextDisplayDimension(dd)
    except Exception:
        dim_count = -1  # 遍历失败不致命
    rec["dimension_count"] = dim_count

    # 简短明确的中文提醒
    if status_code == 2:
        if rec["dimension_count"] == 0:
            rec["advice"] = f"草图「{name}」欠定义：{rec['segment_count']} 个图元没有任何驱动尺寸，拖动图元会改变形状；建议补全尺寸标注"
        else:
            rec["advice"] = f"草图「{name}」欠定义：已有 {rec['dimension_count']} 个尺寸但仍未完全约束；建议检查缺少的长度/角度/定位尺寸"
    elif status_code == 4:
        rec["advice"] = f"草图「{name}」过定义：存在冗余尺寸或几何关系，建议删除冲突标注（SW 中显示为黄色/红色）"
    elif status_code in (5, 6):
        rec["advice"] = f"草图「{name}」无解/无效解：尺寸或几何关系相互矛盾，需人工排查"
    elif status_code == 7:
        rec["advice"] = f"草图「{name}」自动求解已关闭：几何不会随尺寸联动，建议在 SW 中恢复自动求解"
    elif status_code == 3:
        rec["advice"] = f"草图「{name}」完全定义 ✅"
    else:
        rec["advice"] = f"草图「{name}」约束状态未知（code={status_code}），建议人工查看"
    return rec


def check_part(model):
    records = []
    for feat in iter_features(model):
        if is_sketch_feature(feat):
            records.append(sketch_report(feat))

    n_under = sum(1 for r in records if r.get("status_code") == 2)
    n_full = sum(1 for r in records if r.get("status_code") == 3)
    n_over = sum(1 for r in records if r.get("status_code") == 4)
    n_nosol = sum(1 for r in records if r.get("status_code") in (5, 6))
    n_bad = n_under + n_over + n_nosol

    if not records:
        summary = "零件中没有任何草图特征（可能是导入体）"
    elif n_bad == 0:
        summary = f"全部 {n_full} 个草图均为完全定义 ✅"
    else:
        parts = []
        if n_under:
            parts.append(f"{n_under} 个欠定义")
        if n_over:
            parts.append(f"{n_over} 个过定义")
        if n_nosol:
            parts.append(f"{n_nosol} 个无解")
        bad = "、".join(r["sketch"] for r in records if r.get("status_code") in _BAD_CODES)
        summary = f"共 {len(records)} 个草图：{'，'.join(parts)} —— 需处理: {bad}"

    return {
        "title": _safe_title(model),
        "sketch_total": len(records),
        "fully_defined": n_full, "under_defined": n_under,
        "over_defined": n_over, "no_solution": n_nosol,
        "summary": summary,
        "sketches": records,
    }


def fix_sketch(model, sketch_name):
    """进入草图编辑态并 FullyDefineSketch 自动补全约束。返回 (ok, 说明)。
    两次尝试：① 全自动；② 以草图原点为基准（解决轮廓整体漂移漏判）。"""
    dyn = sw_core._dyn(model)
    dyn.ClearSelection2(True)
    if not dyn.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0,
                                     sw_core._empty_callout(), 0):
        return False, f"无法选中草图「{sketch_name}」"
    dyn.EditSketch()
    try:
        # ① 全自动：FullyDefineSketch(全部实体, 用关系, 全部关系4095, 用尺寸,
        #   水平方案0, 水平基准None, 垂直方案0, 垂直基准None, 水平放置0, 垂直放置0)
        model.SketchManager.FullyDefineSketch(True, True, 4095, True,
                                              0, None, 0, None, 0, 0)
        sk = sw_core._early(_active_sketch(model), "ISketch")
        if sk is not None and int(sk.GetConstrainedStatus()) == 3:
            model.SketchManager.InsertSketch(True)
            return True, "已自动补全约束"
        # ② 原点为基准：拾取草图原点 (0,0,0) 作为水平/垂直尺寸基准
        origin = None
        try:
            if dyn.Extension.SelectByID2("", "EXTSKETCHPOINT", 0, 0, 0, False, 0,
                                         sw_core._empty_callout(), 0):
                origin = dyn.SelectionManager.GetSelectedObject6(1, -1)
        except Exception:
            origin = None
        if origin is not None:
            model.SketchManager.FullyDefineSketch(True, True, 4095, True,
                                                  0, origin, 0, origin, 0, 0)
        model.SketchManager.InsertSketch(True)  # 退出草图
        return True, "已自动补全约束（含原点基准尝试）"
    except Exception as exc:
        model.SketchManager.InsertSketch(True)
        return False, f"FullyDefineSketch 失败: {exc}"


def _active_sketch(model):
    """当前编辑中的草图的 ISketch（用于 fix 中途复查）。"""
    try:
        return model.SketchManager.ActiveSketch
    except Exception:
        return None


def fix_part(model, only_under_defined=True):
    """对所有欠定义草图执行自动补全，返回每草图的处理结果。"""
    results = []
    for feat in iter_features(model):
        if not is_sketch_feature(feat):
            continue
        sk = sw_core._early(feat.GetSpecificFeature2(), "ISketch")
        code = int(sk.GetConstrainedStatus())
        if only_under_defined and code != 2:
            continue
        ok, msg = fix_sketch(model, feat.Name)
        # 修复后复查
        sk2 = sw_core._early(feat.GetSpecificFeature2(), "ISketch")
        code2 = int(sk2.GetConstrainedStatus())
        results.append({"sketch": feat.Name, "fix_ok": ok, "message": msg,
                        "status_after": _STATUS_TEXT.get(code2, str(code2)),
                        "status_code_after": code2})
    return results


def _safe_title(model):
    try:
        import sw_core
        return sw_core.com_get(model, "GetTitle")
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="要检查的 .SLDPRT；缺省检查当前活动零件")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 报告")
    ap.add_argument("--fix", action="store_true",
                    help="对欠定义草图自动补全约束（FullyDefineSketch），修复后再出报告")
    args = ap.parse_args()

    sw = sw_core.connect()

    if args.file:
        # 若目标文件已打开则复用，否则打开
        target = os.path.normcase(os.path.abspath(args.file))
        model = None
        for doc in sw_core.com_get(sw_core._dyn(sw), "GetDocuments") or []:
            if os.path.normcase(sw_core.com_get(doc, "GetPathName") or "") == target:
                model = sw_core._early(doc, "IModelDoc2")
                break
        if model is None:
            model = sw_core._early(_open_part(sw, args.file), "IModelDoc2")
        if model is None:
            print(json.dumps({"error": f"无法打开 {args.file}"}, ensure_ascii=False))
            sys.exit(1)
    else:
        model = sw.ActiveDoc
        if model is None:
            print(json.dumps({"error": "SW 中没有活动文档"}, ensure_ascii=False))
            sys.exit(1)
        model = sw_core._early(model, "IModelDoc2")

    if args.fix:
        fix_results = fix_part(model)
        print("== 自动补全约束 ==")
        for fr in fix_results:
            mark = "✅" if fr["fix_ok"] and fr["status_code_after"] == 3 else "⚠️"
            print(f"  {mark} {fr['sketch']}: {fr['message']} → 修复后状态: {fr['status_after']}")
        print()

    report = check_part(model)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"== 草图约束检查: {report['title']} ==")
        print(report["summary"])
        for r in report["sketches"]:
            print(f"  [{r.get('status','?')}] {r.get('advice','')}")
        print()
        print(json.dumps(report, ensure_ascii=False, indent=2))


def _open_part(sw, path):
    import pythoncom
    from win32com.client import VARIANT
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    return sw_core._dyn(sw).OpenDoc6(os.path.abspath(path), 1, 1, "", errors, warnings)


if __name__ == "__main__":
    main()

# 备注：_STATUS_TEXT 映射为 SW 2018 (v26) TLB 实测。
# swConstrainedStatus_e 官方值: 0=swUnderDefined? 本映射已用欠定义草图/全定义草图双向验证。
