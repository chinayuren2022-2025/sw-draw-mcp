"""mcp_server.py — SolidWorks 参数化建模 MCP server（FastMCP，绘图插件发行版 v1.0）

只封装建模能力：透镜/镜筒参数化建模 + 通用零件 spec 建模（DSL）+
两件套装配 + 草图约束自检。
工具：sw_status / lens_dry_run / lens_build / barrel_build / assemble / sketch_check
      / part_spec_dry_run / part_build / feature_create / ref_geometry_create
      / sketch_create / part_inspect / drawing_ingest / drawing_build
      / drawing_compare / annotation_create / subassembly_manage

所有几何计算/建模由 scripts/ 下的 Python 模块确定性执行，本层只做
进程内编排 + JSON 透传，客户端 LLM 只需提取参数字段。

实现要点（实测踩坑）：
- **进程内调用，不用子进程**：子进程方案在 MCP stdio 传输下会卡死
  （孙进程继承传输管道所致）。
- **每个工具调用前 pythoncom.CoInitialize()**：FastMCP 的同步工具跑在
  线程池里，COM 调用必须逐线程初始化。
- **redirect_stdout 屏蔽全部 print**：stdout 是 MCP 协议通道（stdio 模式），
  sw_core 等的 print 会污染协议，必须捕获。
- **全局执行锁串行化**：一个 SW 实例是单线程 COM 服务器，多并发请求必须排队，
  否则 COM 调用会交叉失败。少量并发由锁吸收；大并发请起多个 Windows
  执行节点（VM）做池化。

传输模式：
  stdio（默认，本地客户端）:
    kimi mcp add solidworks-draw --transport stdio -- "<python.exe>" -X utf8 "<本文件>"
  sse（远端平台/虚拟机执行节点）:
    python mcp_server.py --transport sse --host 0.0.0.0 --port 8711
    客户端 mcp.json: {"solidworks-draw": {"url": "http://<VM_IP>:8711/sse"}}

运行：必须用带 pywin32 + mcp 的 Python（见 requirements.txt）。
"""
import argparse
import contextlib
import io
import os
import sys
import threading

from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUTPUT_DIR = os.environ.get("SW_DRAW_OUTPUT",
                            os.path.normpath(os.path.join(HERE, "..", "output")))
os.makedirs(OUTPUT_DIR, exist_ok=True)

mcp = FastMCP("solidworks-draw")

# SW 单实例串行锁：所有工具调用排队执行（少量并发吸收；大并发靠多执行节点）
_SW_LOCK = threading.Lock()


def _call(fn):
    """线程内 COM 初始化 + stdout 屏蔽 + 全局串行锁 + 异常收敛。"""
    import pythoncom
    pythoncom.CoInitialize()
    buf = io.StringIO()
    try:
        with _SW_LOCK:
            with contextlib.redirect_stdout(buf):
                return fn()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        pythoncom.CoUninitialize()


def _connect_model(file=""):
    """连接 SW 并返回 (sw, IModelDoc2)；file 为空取活动文档。"""
    import sw_core
    import sw_sketch_check
    sw = sw_core.connect()
    if file:
        return sw, sw_core._early(sw_sketch_check._open_part(sw, file), "IModelDoc2")
    model = sw.ActiveDoc
    if model is None:
        raise RuntimeError("SW 中没有活动文档，请指定 file 参数")
    return sw, sw_core._early(model, "IModelDoc2")


@mcp.tool()
def sw_status() -> dict:
    """检查本机 SolidWorks 连接状态与版本。不会启动新实例——
    返回 running=false 时表示 SW 未打开（建模类工具会自动启动，但首次较慢）。"""
    def _f():
        import win32com.client
        try:
            sw = win32com.client.GetObject(None, "SldWorks.Application")
        except Exception:
            return {"running": False,
                    "hint": "SolidWorks 未运行；建模/检查工具会自动拉起新实例（首次约 10-30 秒）"}
        doc = sw.ActiveDoc
        title = None
        if doc is not None:
            try:
                title = doc.GetTitle
            except Exception:
                title = None
        return {"running": True, "revision": str(sw.RevisionNumber()),
                "active_doc": title}
    return _call(_f)


@mcp.tool()
def lens_dry_run(params: dict) -> dict:
    """平凸透镜参数推导预览（不建模、不连 SW）。params 示例：
    {"type":"plano_convex","D":25,"f":50,"material":"BK7","tolerance":"standard"}
    返回规范化参数（R/sag/t_c/t_e/chamfer）与约束修正信息，
    展示给用户确认后再调 lens_build。"""
    def _f():
        import optics
        try:
            p, msgs = optics.derive_plano_convex(
                params["D"], params["f"], params["material"],
                params.get("tolerance", "standard"))
        except optics.ConstraintError as e:
            return {"error": f"约束冲突: {e}", "exit_code": 3}
        return {"intent": params, "params": p,
                "messages": [{"level": lv, "text": tx} for lv, tx in msgs]}
    return _call(_f)


@mcp.tool()
def lens_build(params: dict, out: str = "") -> dict:
    """平凸透镜建模+校验+保存。先用 lens_dry_run 给用户确认参数再调本工具。
    params 同 lens_dry_run；out 为 .SLDPRT 保存绝对路径（缺省 output/lens.SLDPRT）。
    返回 steps、体积 SW 实测 vs 理论偏差（应 <1%）、质量估算、保存路径。"""
    def _f():
        import build_lens
        return build_lens.run(params, out or os.path.join(OUTPUT_DIR, "lens.SLDPRT"))
    return _call(_f)


@mcp.tool()
def barrel_build(params: dict, out: str = "") -> dict:
    """镜筒建模+校验+保存。params 示例：
    {"outer_d":27,"bore_d":25.1,"seat_depth":3,"hole_d":23,"length":8}
    （外径/透镜座孔径/座深/通孔径/长度，单位 mm）；out 为 .SLDPRT 保存绝对路径。"""
    def _f():
        import build_barrel
        return build_barrel.run(params, out or os.path.join(OUTPUT_DIR, "barrel.SLDPRT"))
    return _call(_f)


@mcp.tool()
def assemble(insert: str, into: str, save: str = "", spec_only: bool = False,
             sketch_policy: str = "warn") -> dict:
    """两件套装配：把 insert 零件装进 into 零件（自动推导配合 spec + 构建 +
    装配后侧向验证）。文件名可只给 basename（默认在 output/ 解析）。
    spec_only=true 时只输出推导的 spec 不构建，可先给用户过目。
    sketch_policy: warn（默认）/ fix（自动补草图约束）/ strict（欠定义即中止）。"""
    def _f():
        import build_assembly
        import derive_assembly as da
        ins = da._resolve(insert, OUTPUT_DIR)
        into_p = da._resolve(into, OUTPUT_DIR)
        save_p = (save if os.path.isabs(save) else os.path.join(OUTPUT_DIR, save)) \
            or os.path.join(OUTPUT_DIR,
                            os.path.splitext(os.path.basename(into_p))[0] + "_asm.SLDASM")
        sw = da.sw_core.connect()
        carrier_m = da._open_part(sw, into_p)
        insert_m = da._open_part(sw, ins)
        sketch_reports = {"carrier": da.sketch_gate(sw, carrier_m, sketch_policy),
                          "insert": da.sketch_gate(sw, insert_m, sketch_policy)}
        carrier = {"path": into_p, **da._classify_faces(carrier_m)}
        ins_d = {"path": ins, **da._classify_faces(insert_m)}
        spec, info = da.derive_insert_spec(carrier, ins_d, save_p)
        result = {"spec": spec, "info": info,
                  "sketch_check": {k: v["summary"] for k, v in sketch_reports.items()}}
        if spec_only:
            result["spec_only"] = True
            return result
        report = build_assembly.run(spec)
        ok, msg = da.verify_positions(report, info)
        result.update({"verified": ok, "message": msg, "saved": report.get("saved")})
        return result
    return _call(_f)


@mcp.tool()
def sketch_check(file: str = "", fix: bool = False) -> dict:
    """草图约束检查：遍历零件全部草图，报告欠定义/完全定义/过定义/无解，
    附中文处理建议。fix=true 用 SW 原生 FullyDefineSketch 尽力补全后复查。
    file 缺省检查 SW 当前活动零件。建模后的标准自检动作。"""
    def _f():
        import sw_sketch_check
        _, model = _connect_model(file)
        return sw_sketch_check.fix_part(model) if fix else sw_sketch_check.check_part(model)
    return _call(_f)


def _open_or_active(file=""):
    """打开指定零件或取 SW 当前活动文档。"""
    import sw_core
    if file:
        sw = sw_core.connect()
        return sw, sw_core.open_doc(sw, file)
    sw = sw_core.connect()
    model = sw.ActiveDoc
    if model is None:
        raise RuntimeError("SW 中没有活动文档，请指定 file 参数")
    return sw, sw_core._early(model, "IModelDoc2")


@mcp.tool()
def part_spec_dry_run(spec: dict) -> dict:
    """通用零件 spec 预检（不建模、不连 SW）。spec 见 scripts/sw_part_dsl.py 顶部示例：
    units/planes/sketches[{name,plane,entities,dims,relations}]/features[{op,...}]。
    返回校验错误与操作清单；确认后再调 part_build。可用 op 见 scripts/sw_part_dsl.py。"""
    def _f():
        import sw_part_dsl
        return sw_part_dsl.dry_run(spec)
    return _call(_f)


@mcp.tool()
def part_build(spec: dict, out: str = "") -> dict:
    """通用零件建模：解析 spec DSL → 建参考几何/草图/特征 → 深度检查 → 保存。
    out 缺省用 spec.save 或 output/part.SLDPRT。返回 steps、体积、检查报告、保存路径。"""
    def _f():
        import sw_part_dsl
        out_path = out or os.path.join(OUTPUT_DIR, "part.SLDPRT")
        return sw_part_dsl.build_part(spec, out_path=out_path)
    return _call(_f)


@mcp.tool()
def feature_create(file: str = "", feature: dict = None) -> dict:
    """在已打开/指定零件上执行单个特征。feature 与 part_build 的 features 元素一致，
    例：{"op":"fillet","radius_mm":1,"edge_specs":{"type":"circle","radius_mm":5}}。
    草图类 op 请用 sketch_create。返回特征名与执行摘要。"""
    def _f():
        import sw_features
        import sw_part_dsl
        feature = feature or {}
        _, model = _open_or_active(file)
        mod_name = sw_part_dsl._FEATURE_OPS[feature["op"]][0]
        mod = __import__(mod_name)
        feat = sw_part_dsl._apply_feature(mod, model, feature, {})
        return {"feature": getattr(feat, "Name", str(feat)), "op": feature.get("op")}
    return _call(_f)


@mcp.tool()
def ref_geometry_create(file: str = "", spec: dict = None) -> dict:
    """在已打开/指定零件上创建参考几何。spec 例：
    {"op":"ref_plane","plane_type":"offset","base":"front","distance_mm":10}
    或 {"op":"ref_axis","axis_type":"cylinder","base_spec":{"kind":"cylinder","radius_mm":5}}。"""
    def _f():
        import sw_part_dsl
        spec = spec or {}
        _, model = _open_or_active(file)
        mod = __import__(sw_part_dsl._FEATURE_OPS[spec["op"]][0])
        ret = sw_part_dsl._apply_feature(mod, model, spec, {})
        return {"result": str(ret)}
    return _call(_f)


@mcp.tool()
def assembly_spec_dry_run(spec: dict) -> dict:
    """通用装配 spec 预检（不建模）。spec 结构见 scripts/sw_assembly_full.run_spec：
    components[{path,at,config_option,config_name,fix,visible,suppression}] /
    mates[{face1,face2,mate_type,align,distance_m,angle_deg,...}] /
    patterns / checks / save。返回字段校验结果。"""
    def _f():
        spec = spec or {}
        errors = []
        if not isinstance(spec.get("components") or [], list):
            errors.append("components 必须是列表")
        for i, c in enumerate(spec.get("components") or []):
            if not isinstance(c, dict) or "path" not in c:
                errors.append(f"components[{i}] 缺少 path")
        for i, m in enumerate(spec.get("mates") or []):
            if not isinstance(m, dict) or "mate_type" not in m:
                errors.append(f"mates[{i}] 缺少 mate_type")
        return {"valid": not errors, "errors": errors,
                "component_count": len(spec.get("components") or []),
                "mate_count": len(spec.get("mates") or [])}
    return _call(_f)


@mcp.tool()
def assembly_build(spec: dict, out: str = "") -> dict:
    """通用装配体建模：解析 spec → 插入零部件 → 配合/阵列 → 检查 → 保存。
    spec 结构见 assembly_spec_dry_run；out 缺省用 spec.save 或 output/assembly.SLDASM。"""
    def _f():
        import sw_assembly_full
        spec = spec or {}
        if out and "save" not in spec:
            spec = dict(spec, save=out)
        if not spec.get("save"):
            spec = dict(spec, save=os.path.join(OUTPUT_DIR, "assembly.SLDASM"))
        return sw_assembly_full.run_spec(spec)
    return _call(_f)


@mcp.tool()
def sketch_create(file: str = "", plane: str = "front", entities: list = [],
                  dims: list = [], relations: list = []) -> dict:
    """在已打开/指定零件上创建独立草图（不生成特征）。plane 可为 front/top/right 或
    已有基准面名；entities 元素同 part_build 草图实体（单位 mm）。"""
    def _f():
        import sw_sketch
        _, model = _open_or_active(file)
        sw_sketch.start_sketch(model, plane)
        for e in entities:
            import sw_part_dsl
            sw_part_dsl._draw_entity(sw_sketch, model, e)
        spec = {"dims": dims, "relations": relations}
        import sw_part_dsl
        sw_part_dsl._apply_sketch_extra(sw_sketch, model, spec)
        sw_sketch.end_sketch(model)
        name = sw_part_dsl._capture_sketch_name(model, "sketch", sw_sketch)
        return {"sketch": name, "entity_count": len(entities)}
    return _call(_f)


@mcp.tool()
def part_inspect(file: str = "") -> dict:
    """零件深度检查：草图约束 + 草图质量 + 特征树错误码 + 重建/What's Wrong + 多实体初筛。"""
    def _f():
        import sw_check
        _, model = _open_or_active(file)
        return sw_check.deep_check(model)
    return _call(_f)


@mcp.tool()
def drawing_ingest(input: str, out_dir: str = "") -> dict:
    """工程图解析：输入 PDF/图片，输出结构化 drawing.json（视图裁剪图、文本尺寸、页面信息）。
    out_dir 缺省 output/drawing/<stem>。不连接 SolidWorks。"""
    def _f():
        import drawing_ingest
        return drawing_ingest.ingest(input, out_dir=out_dir or None)
    return _call(_f)


@mcp.tool()
def drawing_build(spec: dict, out: str = "") -> dict:
    """按 drawing_spec JSON 建模（可在客户端先画草图再建模）。
    spec 示例见 examples/mm25/drawing_spec.json；out 缺省用 spec.output 或 output/<name>.SLDPRT。
    返回特征名、保存路径。"""
    def _f():
        import drawing_spec
        return drawing_spec.run_spec(spec, save=out or None)
    return _call(_f)


@mcp.tool()
def drawing_compare(drawing_json: str, model_views_dir: str,
                    mapping: str = "", use_cv: bool = False) -> dict:
    """模型视图 vs 图纸视图差异检测：默认只生成 side_by_side 图（无 OpenCV 依赖）。
    use_cv=True 时才启用 OpenCV 边缘/圆识别。
    mapping 形如 front=crop_00.png,top=crop_01.png；缺省使用 mm25 默认映射。"""
    def _f():
        import model_view_compare
        mapping_dict = {}
        if mapping:
            for part in mapping.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    mapping_dict[k.strip()] = v.strip()
        return model_view_compare.compare(drawing_json, model_views_dir,
                                          mapping=mapping_dict or None,
                                          enable_cv=bool(use_cv))
    return _call(_f)


@mcp.tool()
def annotation_create(file: str = "", op: str = "dimxpert_add_dimension",
                      dim_type: str = "size", face_spec: dict = None,
                      config_name: str = "默认") -> dict:
    """零件级尺寸标注（DimXpert/MBD 基础）。op ∈ dimxpert_add_dimension /
    dimxpert_auto_dimension / dimxpert_counts / dimxpert_delete_tolerances。
    dim_type ∈ size / location / basic；face_spec 为 sw_sel 面 spec。"""
    def _f():
        import sw_annotate
        _, model = _open_or_active(file)
        if op == "dimxpert_counts":
            return sw_annotate.dimxpert_counts(model, config_name=config_name)
        if op == "dimxpert_auto_dimension":
            return sw_annotate.dimxpert_auto_dimension(model, config_name=config_name)
        if op == "dimxpert_delete_tolerances":
            return sw_annotate.dimxpert_delete_tolerances(model, config_name=config_name)
        return sw_annotate.dimxpert_add_dimension(
            model, dim_type=dim_type, face_spec=face_spec, config_name=config_name)
    return _call(_f)


@mcp.tool()
def subassembly_manage(file: str = "", op: str = "insert", comp: str = "",
                       path: str = "", config_name: str = "",
                       x: float = 0, y: float = 0, z: float = 0) -> dict:
    """子装配体管理。op ∈ insert（插入已有装配体路径）/ dissolve（解散组件）/
    edit（进入组件编辑模式）。file 为顶层装配体路径；comp 为组件 Name2。"""
    def _f():
        import sw_assembly_full
        sw = sw_core.connect()
        asm = sw_core.open_doc(sw, file, doc_type=2) if file else sw.ActiveDoc
        if asm is None:
            raise RuntimeError("请指定 file 或在 SW 中打开装配体")
        asm = sw_core._early(asm, "IModelDoc2")
        if op == "insert":
            comp = sw_assembly_full.insert_subassembly(
                asm, path, config_name=config_name, x=x, y=y, z=z)
            return {"component": sw_assembly_full._comp_name(comp)}
        c = sw_assembly_full.find_component(asm, comp)
        if op == "dissolve":
            return {"dissolved": sw_assembly_full.dissolve_subassembly(asm, c)}
        if op == "edit":
            return {"editing": sw_assembly_full.edit_subassembly(asm, c)}
        raise RuntimeError(f"不支持的 op: {op}")
    return _call(_f)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                    help="stdio=本地客户端（默认）；sse=HTTP 服务（远端平台/VM 执行节点）")
    ap.add_argument("--host", default="0.0.0.0", help="SSE 监听地址")
    ap.add_argument("--port", type=int, default=8711, help="SSE 监听端口（绘图插件默认 8711，与审图插件 8710 区分）")
    args = ap.parse_args()
    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"[mcp_server] SSE 模式: http://{args.host}:{args.port}/sse", file=sys.stderr)
    mcp.run(transport=args.transport)
