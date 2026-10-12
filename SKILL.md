---
name: sw-draw-skill
description: 自然语言驱动本机 SolidWorks 参数化建模（平凸透镜/镜筒/两件套装配）。LLM 只负责意图提取与编排，几何计算/查表/约束验证全部由 Python 确定性执行。适用于 Windows + 本机已安装 SolidWorks（COM 已注册）+ Python + pywin32 的环境。
---

# SolidWorks AI 绘图插件（参数化建模）

## 何时使用

用户要求"画/建/生成 一个透镜/镜筒/光学零件"并给出直径、焦距、材料等参数时；
用户要求绘制**任意参数化零件**（法兰、孔板、回转体、含圆角/阵列/孔的常见机械件）时；
或要求把已生成的两个零件**装配**起来（2 件、同轴心/距离配合）。
不要用于：工程图检查（那是审图插件 sw-check-skill）、钣金/焊件（P3 暂未启用）。

## 核心原则（必须遵守）

1. **LLM 不做数值计算**。折射率、曲率半径、厚度、矢高全部由 `scripts/optics.py` 计算。
2. **LLM 不直接调 SW API**。只调用特征级入口（build_lens / build_barrel / derive_assembly / part_build / feature_create 等）。
3. **先展示参数，确认后建模**。`lens_dry_run` / `part_spec_dry_run` / `assemble(spec_only=true)`
   输出推导结果，用户确认后再真正建模。

## 运行前提

- Python 环境有 pywin32 + mcp：`pip install -r requirements.txt`
- 首次运行已生成 COM 早绑定缓存（见 README 安装第 3 步）
- SolidWorks 已打开（推荐）或允许脚本启动新实例

## MCP 工具（19 个）

| 工具 | 作用 |
|---|---|
| `sw_status` | SW 连接/版本探活 |
| `lens_dry_run` | 透镜参数推导预览（不建模） |
| `lens_build` | 平凸透镜建模+校验+保存 |
| `barrel_build` | 镜筒建模+校验+保存 |
| `assemble` | 两件套装配（自动推导 spec + 构建 + 侧向验证） |
| `sketch_check` | 草图约束检查（建模后标准自检，可 fix） |
| `part_spec_dry_run` | 通用零件 spec 预检（不建模） |
| `part_build` | 通用零件建模（spec DSL → 特征 → 深度检查 → 保存） |
| `feature_create` | 在已打开/指定零件上执行单个特征 |
| `ref_geometry_create` | 创建基准面/轴/点/坐标系 |
| `sketch_create` | 在已打开/指定零件上创建独立草图 |
| `part_inspect` | 零件深度检查（约束/特征错误/重建/多实体） |
| `assembly_spec_dry_run` | 通用装配 spec 预检 |
| `assembly_build` | 通用装配体建模（配合/组件状态/阵列/检查/保存） |
| `drawing_ingest` | 工程图解析：PDF/图片 → 视图裁剪图 + 文本/尺寸 JSON |
| `drawing_build` | 按 drawing_spec 建模并保存，强制执行回拍校验 |
| `drawing_compare` | 模型视图 vs 图纸视图差异检测报告（`use_cv=false` 默认关闭 OpenCV） |
| `annotation_create` | DimXpert/MBD 零件尺寸标注（size/location/basic/auto） |
| `subassembly_manage` | 子装配体插入/解散/编辑 |

## 通用零件 spec（part_build）

```json
{
  "units": "mm",
  "planes": [{"name": "P1", "type": "offset", "base": "front", "distance_mm": 10}],
  "sketches": [
    {"name": "sk1", "plane": "front",
     "entities": [{"type": "corner_rectangle", "x1": 0, "y1": 0, "x2": 20, "y2": 10}],
     "dims": [{"kind": "linear", "p1": [0,0], "p2": [20,0], "horizontal": true,
               "text": [10,-2]}],
     "relations": [{"type": "horizontal", "targets": [0]}]}
  ],
  "features": [{"op": "extrude_boss", "sketch": "sk1", "depth_mm": 5}],
  "save": "flange.SLDPRT"
}
```

可用 op 见 `scripts/sw_part_dsl.py`（`python -c "import sys;sys.path.insert(0,'scripts');import sw_part_dsl;print(sw_part_dsl.ops_available())"`）。

## 直接 CLI（不经 MCP）

```bash
python scripts/build_lens.py --params '{"type":"plano_convex","D":25,"f":50,"material":"BK7"}' --dry-run
python scripts/build_lens.py --params '<JSON>' --out output/lens.SLDPRT
python scripts/derive_assembly.py --intent '{"action":"insert","insert":"a.SLDPRT","into":"b.SLDPRT","save":"c.SLDASM"}'
python scripts/build_mm25.py    # 按工程图 mm25-p1-1.pdf 近似建模，输出 output/mm25_p1_1.SLDPRT
python scripts/capture_model_views.py  # 导出前/后/左/右/上/下/等轴测 PNG 到 output/views/
python scripts/drawing_ingest.py <drawing.pdf>   # 解析工程图 → output/drawing/<stem>/
python scripts/drawing_interpret.py output/drawing/<stem>/drawing.json              # 默认不启用 CV
python scripts/drawing_interpret.py output/drawing/<stem>/drawing.json --cv          # 可选启用 OpenCV
python scripts/model_view_compare.py output/drawing/<stem>/drawing.json output/views  # 默认 side-by-side
python scripts/model_view_compare.py output/drawing/<stem>/drawing.json output/views --cv  # 可选 CV
python scripts/sw_sketch_check.py --file output/lens.SLDPRT [--fix]
```

## 测试与实机桥接

- WSL→PowerShell 7→Windows Python 实机脚本在 `bridge/`；测试说明与已知边界见 `docs/TESTING.md`。
- 三套实机测试：`integration_sw2018.py`（基础 13）、`integration_part_advanced.py`（高级 9）、`integration_assembly.py`（装配 10）。
- 读图建模实机回归：`scripts/tests/integration_drawing.py`（mm25 drawing_spec 全流程）。
- 扩展功能实机回归：`scripts/tests/integration_extended.py`（装饰螺纹/特征树/DimXpert/子装配体）。

## 知识库

- `knowledge/optical.md`：透镜公式、标准直径系列、厚度/倒角约束
- `knowledge/materials.md`：光学玻璃与金属材料表（折射率/阿贝数/密度）
- `knowledge/drawing_reading.md`：读图规则、剖视/盲腔/通孔判断、TYP 圆角、SW 视图名坑

## 故障速查（节选）

| 报错 | 处理 |
|---|---|
| `类型不匹配 (-2147352571)` | sw_core 已处理 VARIANT 传参，确认用的是包内脚本 |
| `非选择性的参数 (-2147352561)` | FeatureRevolve2 签名随 SW 版本变，换版本后重跑 makepy 核对 |
| 基准面选择失败 | sw_part 内置双语候选（前视基准面/Front Plane） |
| 配合 err=5 | 轴向定位用 distance(d=0)，不要 concentric+coincident 叠加 |
| 保存失败 err=1 | 同名文档已在 SW 打开；save_as 已自动处理，仍失败查只读/权限 |

详细踩坑记录见主项目 docs/（功能一/功能二专项文档）。
