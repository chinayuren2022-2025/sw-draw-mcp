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
        import sw_core
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


# ---------------------------------------------------------------------------
# 文档 / 拓扑 / 闭环验证 / 装配配合（v2 新增）
#
# 推荐 AI 工作流：
#   零件：part_build -> part_topology（看面与持久 ID）-> entity_name 给配合面起名
#         -> view_capture 看结果 -> dimension_list / dimension_set 改参数
#   装配：asm_insert -> asm_mate（按"组件+面名"）-> 看返回的 status / remaining_dofs
#         -> asm_check（欠定义/过定义/干涉）-> view_capture
# ---------------------------------------------------------------------------

def _doc(file=""):
    """(sw, IModelDoc2)：file 为路径（自动按扩展名打开）、已打开文档标题，或空=活动文档。"""
    import sw_core
    import sw_doc
    sw = sw_core.connect()
    if file:
        if os.path.isfile(file) or os.path.splitext(file)[1]:
            try:
                return sw, sw_core._early(sw_doc.find_open(sw, file), "IModelDoc2")
            except RuntimeError:
                return sw, sw_doc.open_document(sw, file)
        return sw, sw_core._early(sw_doc.find_open(sw, file), "IModelDoc2")
    model = sw.ActiveDoc
    if model is None:
        raise RuntimeError("SW 中没有活动文档，请指定 file（路径或已打开文档标题）")
    return sw, sw_core._early(model, "IModelDoc2")


def _is_asm(model):
    try:
        return int(model.GetType()) == 2
    except Exception:
        return False


@mcp.tool()
def doc_list() -> dict:
    """列出 SW 中已打开的文档（标题、路径、类型、是否活动、是否有未保存修改）。"""
    def _f():
        import sw_core
        import sw_doc
        return {"documents": sw_doc.documents(sw_core.connect())}
    return _call(_f)


@mcp.tool()
def doc_open(path: str) -> dict:
    """打开 .SLDPRT/.SLDASM/.SLDDRW 并设为活动文档（已打开则直接激活）。"""
    def _f():
        import sw_core
        _, model = _doc(path)
        return {"title": sw_core.model_title(model), "path": sw_core.model_path(model)}
    return _call(_f)


@mcp.tool()
def doc_save(file: str = "", path: str = "") -> dict:
    """保存文档。path 为空则原地保存（新文档必须给 path，扩展名决定类型）。"""
    def _f():
        import sw_doc
        sw, model = _doc(file)
        return sw_doc.save(sw, model, path)
    return _call(_f)


@mcp.tool()
def doc_close(file: str = "", save: bool = False) -> dict:
    """关闭文档（file 为标题或路径，空=活动文档）。save=false 时丢弃未保存修改。"""
    def _f():
        import sw_doc
        sw, model = _doc(file)
        return sw_doc.close(sw, model, save_first=save)
    return _call(_f)


@mcp.tool()
def doc_export(path: str, file: str = "") -> dict:
    """按扩展名导出：.step/.stp/.igs/.stl/.x_t/.x_b/.sat/.3mf/.pdf/.dxf/.dwg/.eprt/.easm。"""
    def _f():
        import sw_doc
        sw, model = _doc(file)
        return sw_doc.export(sw, model, path)
    return _call(_f)


@mcp.tool()
def view_capture(file: str = "", view: str = "isometric", width: int = 1200,
                 height: int = 900, save_to: str = ""):
    """截取模型视图并直接返回图片，供 AI 目视检查建模结果。
    view ∈ isometric/front/back/left/right/top/bottom/trimetric/dimetric/current。"""
    from mcp.server.fastmcp import Image

    def _f():
        import sw_doc
        sw, model = _doc(file)
        return sw_doc.capture(sw, model, view, width, height, save_to)
    res = _call(_f)
    if isinstance(res, dict):
        return res
    png_path, data = res
    return [f"{view} 视图：{png_path}", Image(data=data, format="png")]


@mcp.tool()
def feature_list(file: str = "", include_sub: bool = True) -> dict:
    """列出特征树：名称、类型、压缩状态、错误码；include_sub 含草图等子特征。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return {"features": sw_doc.features(model, include_sub=include_sub)}
    return _call(_f)


@mcp.tool()
def feature_suppress(name: str, suppress: bool = True, file: str = "") -> dict:
    """压缩/解压缩特征（可逆；排查问题优先用它而不是删除）。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return sw_doc.suppress_feature(model, name, suppress)
    return _call(_f)


@mcp.tool()
def feature_delete(name: str, file: str = "", keep_absorbed: bool = False) -> dict:
    """删除特征（默认连同其草图）；返回实际被删除的全部特征（含级联删除的子特征）。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return sw_doc.delete_feature(model, name, keep_absorbed)
    return _call(_f)


@mcp.tool()
def undo(count: int = 1, file: str = "") -> dict:
    """撤销最近 count 步操作，返回撤销前后特征数以确认是否生效。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return sw_doc.undo(model, count)
    return _call(_f)


@mcp.tool()
def dimension_list(file: str = "", feature: str = "") -> dict:
    """列出尺寸全名与当前值（mm / deg），如 D1@草图1；feature 可限定某个特征。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return {"dimensions": sw_doc.dimensions(model, feature or None)}
    return _call(_f)


@mcp.tool()
def dimension_set(name: str, value: float, file: str = "") -> dict:
    """按全名修改尺寸并重建；长度单位 mm、角度单位 deg（按尺寸类型自动判断）。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        return sw_doc.set_dimension(model, name, value)
    return _call(_f)


@mcp.tool()
def custom_properties(file: str = "", props: dict = None, config: str = "") -> dict:
    """读/写文件自定义属性（props 为 {名称: 值} 时写入，否则只读）。config 为空=文件级。"""
    def _f():
        import sw_doc
        _, model = _doc(file)
        if props:
            return sw_doc.set_custom_properties(model, props, config)
        return {"properties": sw_doc.custom_properties(model, config)}
    return _call(_f)


@mcp.tool()
def part_topology(file: str = "", kind: str = "", include_edges: bool = False,
                  limit: int = 200) -> dict:
    """列出零件的面（及边）：类型、法向/轴/半径、面积、包围盒、名字、persist_id。
    persist_id / name 可用于 entity_name、measure、asm_mate 等工具的 ref，
    重建后依然有效（比 Face<n> 或坐标稳定）。kind 过滤 plane/cylinder/cone/sphere/torus。"""
    def _f():
        import sw_topo
        _, model = _doc(file)
        include = ("faces", "edges") if include_edges else ("faces",)
        return sw_topo.topology(model, include=include, kind=kind or None, limit=limit)
    return _call(_f)


@mcp.tool()
def entity_name(ref: dict, name: str, file: str = "", save: bool = True) -> dict:
    """给零件的面/边/顶点起名（存入零件文件），之后装配中用 {"component":..,"face":name} 引用。
    ref 任选：{"persist_id":..} / {"spec":{"kind":"cylinder","radius_mm":5}} /
    {"ray":{"origin_mm":[0,0,50],"direction":[0,0,-1]}} / {"index":3}。
    spec 平面示例：{"kind":"plane","normal":[0,0,1],"directional":true,"root_mm":[0,0,10]}
    （normal 是实体外法向；root_mm 是平面上任一点）。"""
    def _f():
        import sw_doc
        import sw_topo
        sw, model = _doc(file)
        ent, kind = sw_topo.resolve(model, ref)
        sw_topo.name_entity(model, ent, name)
        out = {"named": name, "kind": kind, "persist_id": sw_topo.persist_id(model, ent)}
        if save:
            out.update(sw_doc.save(sw, model))
        return out
    return _call(_f)


@mcp.tool()
def measure(ref1: dict, ref2: dict = None, file: str = "") -> dict:
    """测量（IMeasure）：距离/法向距离/中心距/角度/半径/面积/平行/垂直等。
    零件中 ref 同 entity_name；装配中 ref 同 asm_mate（{"component":..,"face":..}）。"""
    def _f():
        import sw_asm_ref
        import sw_topo
        _, model = _doc(file)
        if _is_asm(model):
            ents = []
            for r in [ref1] + ([ref2] if ref2 else []):
                how, obj, desc = sw_asm_ref.resolve(model, r)
                if how != "entity":
                    raise RuntimeError(f"测量暂不支持基准面/轴引用：{desc}")
                ents.append(obj)
            return sw_topo.measure_entities(model, ents)
        return sw_topo.measure(model, ref1, ref2)
    return _call(_f)


@mcp.tool()
def mass_properties(file: str = "") -> dict:
    """体积(mm³)/表面积/质量/密度/质心(mm)/包围盒，零件或装配体均可。用于建模后验证。"""
    def _f():
        import sw_topo
        _, model = _doc(file)
        return sw_topo.mass(model)
    return _call(_f)


@mcp.tool()
def asm_new(save: str = "") -> dict:
    """新建空装配体（save 给路径则立即保存）。"""
    def _f():
        import sw_assembly
        import sw_core
        import sw_doc
        sw = sw_core.connect()
        asm = sw_core._early(sw_assembly.new_assembly(sw), "IModelDoc2")
        out = {"title": sw_core.model_title(asm)}
        if save:
            out.update(sw_doc.save(sw, asm, save))
        return out
    return _call(_f)


@mcp.tool()
def asm_insert(path: str, at_mm: list = [0, 0, 0], place: str = "origin",
               fix: bool = None, file: str = "") -> dict:
    """插入零件/子装配。place="origin"：零件原点精确落在 at_mm（推荐）；
    "bbox_center"：SW 原生语义（包围盒中心落在 at_mm）。第一个组件默认被 SW 固定。
    返回组件名（后续 ref 用）、约束状态、原点、包围盒。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.insert_component(asm, path, at_mm, place, fix)
    return _call(_f)


@mcp.tool()
def asm_components(file: str = "", top_level: bool = True) -> dict:
    """列出组件：名称、路径、固定、约束状态（under/fully/over_constrained）、
    剩余自由度（转轴/平移方向）、原点与旋转矩阵、包围盒、配合数。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return {"components": sw_asm_ref.assembly_components(asm, top_level)}
    return _call(_f)


@mcp.tool()
def asm_component_faces(component: str, file: str = "", kind: str = "",
                        include_edges: bool = False, limit: int = 200) -> dict:
    """列出组件的面（装配坐标）：类型、法向/轴、半径、包围盒、名字、persist_id。
    用返回的 name 或 persist_id 写 asm_mate 的 ref。kind 过滤 plane/cylinder/...。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.comp_faces(asm, component, kind or None, limit, include_edges)
    return _call(_f)


@mcp.tool()
def asm_mate(a: dict, b: dict, mate_type: str = "coincident", align: str = "closest",
             flip: bool = False, distance_mm: float = 0, angle_deg: float = 0,
             extra: list = None, rollback_on_error: bool = True, file: str = "") -> dict:
    """闭环配合：选择 -> 配合 -> 重建 -> 返回两端组件的约束状态与剩余自由度。
    ref 写法（a/b）：
      {"component":"pin-1","face":"PIN_CYL"}   零件中已命名的面（entity_name），最稳
      {"component":"pin-1","persist_id":".."}  asm_component_faces 返回的 ID
      {"component":"pin-1","plane":"front"}    组件基准面 front/top/right/自定义名
      {"component":"pin-1","axis":"基准轴1"} / {"component":"pin-1","point":"origin"}
      {"component":"pin-1","spec":{"kind":"cylinder","radius_mm":5}}（零件局部坐标）
      {"plane":"front"}                        装配体自身基准面
    mate_type: coincident/concentric/perpendicular/parallel/tangent/distance/angle/
      symmetric/width/gear/rack_pinion/screw/lock/hinge/slot/slider/path/...
    align: aligned/anti/closest；distance_mm/angle_deg 仅距离/角度配合用。
    extra: [{"ref":{..},"mark":2}] 对称面等第三选择。
    过定义/冲突时返回 ok=false 并自动删除该配合（rollback_on_error）。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.mate(asm, a, b, mate_type, align, flip, distance_mm, angle_deg,
                               extra, rollback_on_error)
    return _call(_f)


@mcp.tool()
def asm_mates(file: str = "") -> dict:
    """列出全部配合：类型、对齐、翻转、两端组件与实体类型、数值(mm/deg)、错误码、压缩状态。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return {"mates": sw_asm_ref.mates(asm)}
    return _call(_f)


@mcp.tool()
def asm_mate_edit(name: str, distance_mm: float = None, angle_deg: float = None,
                  flip: bool = None, file: str = "") -> dict:
    """修改配合的距离/角度值或翻转方向，重建后返回新的配合详情。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.edit_mate(asm, name, distance_mm, angle_deg, flip)
    return _call(_f)


@mcp.tool()
def asm_mate_delete(name: str, file: str = "") -> dict:
    """删除配合。"""
    def _f():
        import sw_assembly_full
        import sw_core
        _, asm = _doc(file)
        sw_assembly_full.delete_mate(asm, name)
        sw_core.rebuild(asm)
        return {"deleted": name}
    return _call(_f)


@mcp.tool()
def asm_mate_suppress(name: str, suppress: bool = True, file: str = "") -> dict:
    """压缩/解压缩配合（可逆，用于排查哪条配合导致冲突）。"""
    def _f():
        import sw_assembly_full
        import sw_core
        _, asm = _doc(file)
        ok = sw_assembly_full.suppress_mate(asm, name, suppress)
        sw_core.rebuild(asm)
        return {"mate": name, "suppressed": suppress, "ok": ok}
    return _call(_f)


@mcp.tool()
def asm_move(component: str, delta_mm: list = None, to_mm: list = None,
             file: str = "") -> dict:
    """平移组件：delta_mm 相对移动，或 to_mm 把零件原点移到指定位置。
    组件受配合约束时由求解器决定最终位置（返回实际原点）。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.move_component(asm, component, delta_mm, to_mm)
    return _call(_f)


@mcp.tool()
def asm_fix(component: str, fixed: bool = True, file: str = "") -> dict:
    """固定 / 浮动组件。"""
    def _f():
        import sw_asm_ref
        import sw_assembly_full as af
        _, asm = _doc(file)
        comp = sw_asm_ref.find_comp(asm, component)
        (af.fix_component if fixed else af.float_component)(asm, comp)
        return sw_asm_ref.comp_info(asm, comp)
    return _call(_f)


@mcp.tool()
def asm_check(file: str = "", interference: bool = True) -> dict:
    """装配闭环检查：重建、配合错误、欠定义组件(floating)、过定义组件、精确干涉、What's Wrong。
    ok=true 表示无错误、无过定义、无干涉（欠定义不算错误，单独列在 floating）。"""
    def _f():
        import sw_asm_ref
        _, asm = _doc(file)
        return sw_asm_ref.check(asm, with_interference=interference)
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
