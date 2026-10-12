# -*- coding: utf-8 -*-
"""读图建模工作流实机集成测试（SW2018）。

覆盖：
  - drawing_spec 按 mm25 spec 建模（展台/两孔/腰形盲腔/镜像/Ø35/R2）
  - 保存并确认文件存在

用法：
    python integration_drawing.py [--strict]
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SPEC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "..", "examples", "mm25", "drawing_spec.json")


def _run(name, fn):
    print(f"[draw] RUN {name}", file=sys.stderr, flush=True)
    try:
        detail = fn()
        print(f"[draw] PASS {name}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": True, "detail": detail}
    except Exception as exc:
        print(f"[draw] FAIL {name}: {exc}", file=sys.stderr, flush=True)
        return {"scenario": name, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def s_build_from_spec():
    import drawing_spec
    with open(SPEC, "r", encoding="utf-8") as f:
        spec = json.load(f)
    r = drawing_spec.run_spec(spec)
    assert os.path.exists(r["saved"]), "保存文件不存在"
    needed = ["凸台-拉伸1", "切除-拉伸1", "切除-拉伸2", "镜向1", "孔1", "圆角1"]
    names = list(r.get("features", {}).values())
    missing = [n for n in needed if n not in names]
    if missing:
        raise AssertionError(f"缺少特征: {missing}, 实际: {names}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json-out", default="",
                    help="把最终 JSON 写到该路径（不影响 stdout 日志）")
    args = ap.parse_args()
    results = [
        _run("drawing_spec_mm25", s_build_from_spec),
    ]
    failed = [r for r in results if not r["ok"]]
    payload = {"results": results, "failed": len(failed),
               "strict": bool(args.strict)}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("json written:", args.json_out, file=sys.stderr, flush=True)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
