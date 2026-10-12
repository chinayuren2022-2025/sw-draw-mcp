# 读图建模工作流改进方案（已审核）

> 目标：为 `sw-draw-skill` 增加一条一等公民工作流：
> `工程图 → 图纸解析 → 视图理解 → 可审计建模 spec → 确定性建模 → 实机多视图回拍 → 差异报告 → 修正`
> 识图能力采用可插拔设计：有视觉模型时用视觉模型；程序化 CV 默认关闭（`--cv`/`use_cv=true` 才启用），
> 核心功能只依赖 Pillow，OpenCV 为可选依赖（`requirements-cv.txt`）。

## 0. 问题复盘（以 mm25-p1-1 为例）

1. 只解析 PDF 文字尺寸，没有系统提取视图布局。
2. 中央特征误判：文字尺寸下以为是 50×50 矩形通槽，实为“前后各 20mm 盲腔 + 中间实体 + 两侧内凹腰形”。
3. `R2 TYP ALL RED FILLETS` 被当成可选项，实际是必建圆角。
4. 视图→SW 坐标平面映射缺乏固定规则，导致 Ø35 孔初期在 Top Plane 上反复失败。
5. 缺少建模后强制回拍对比，错误直到用户发现才被修正。

## 1. 总体架构

```text
工程图(PDF/图片) → drawing_ingest → drawing_interpret
        → drawing_spec → drawing_build
        → capture_model_views → model_view_compare → 差异报告 → 修正
```

新增 MCP 工具：

| 工具 | 作用 |
|---|---|
| `drawing_ingest` | 解析 PDF/图片，输出视图分块、文字尺寸、图元候选、JSON |
| `drawing_build` | 依据 drawing spec 建模，并强制执行回拍校验 |
| `drawing_compare` | 模型视图 vs 图纸视图差异检测报告 |

## 2. 图纸解析层（drawing_ingest.py）

输入 PDF/PNG/JPG，输出 `drawing_views.json`：

```json
{
  "source": "mm25-p1-1.pdf",
  "projection": "third_angle",
  "units": "mm",
  "views": [
    {
      "id": "front",
      "bbox": [x0,y0,x1,y1],
      "image": "crop_front.png",
      "text_dims": [],
      "detected": {
        "outer_contours": [],
        "holes": [],
        "slots": []
      }
    }
  ],
  "sections": [
    {"id": "A_A", "image": "...", "dims": []},
    {"id": "B_B", "image": "...", "dims": []}
  ],
  "notes": ["R2 TYP ALL RED FILLETS", "ALL DIMENSIONS ARE IN MILLIMETERS"]
}
```

要点：

- PyMuPDF 高 DPI 渲染整页；提取内嵌图片（已验证可行）。
- PDF 原生 text 优先；扫描件用可插拔 OCR（Windows OCR / tesseract / PaddleOCR）。
- 按标题栏、边框、视图间距、Section 标签切分视图。
- 识别 `THIRD ANGLE PROJECTION` / `FIRST ANGLE`。
- 支持 `150`、`Ø40`、`R30`、`R2 TYP`、`35 THRU`、`SECTION A-A` 等写法。

## 3. 视图理解层（drawing_interpret.py）

- 2D 图元检测：二值化、轮廓、HoughCircles、HoughLinesP、剖面线识别。
- 视图间对齐规则（第三角投影）。
- 剖视图作为深度/壁厚/盲腔的权威证据。
- 输出 feature hypothesis，每条带 `confidence`、`evidence`、`alternatives`。

## 4. 确定性建模层（drawing_spec + drawing_build）

- 定义 `drawing_spec` schema，比 `part_spec` 多“依据/校验”字段。
- 固化视图→SW 坐标映射：
  - 工程图 Front → SW Front Plane（XY）
  - 工程图 Top → SW Top Plane（XZ，Y 向观察）
  - 工程图 Right → SW Right Plane（YZ，X 向观察）
- 对称特征优先用镜像/阵列。
- `TYP` 圆角/倒角必须进入 spec。
- 输出 `output/*_audit.json`：SW 特征名 ↔ spec 特征 ↔ 图纸证据链。

## 5. 实机回拍校验闭环（核心）

新增 `model_view_compare.py`，`drawing_build` 强制调用：

1. 复用 `capture_model_views.py` 输出模型前/上/右/等轴测。
2. 从 drawing_ingest 取图纸对应视图裁剪图。
3. 对齐：按外轮廓包围盒仿射对齐。
4. 指标：轮廓 IoU、边缘距离（Chamfer/Hausdorff）、HoughCircles 孔差异。
5. 差异分类：缺失特征 / 类型错误 / 方向错误 / 尺寸偏差 / 位置偏差。
6. 输出 `output/*_compare.json`。
7. 视觉模型可用时并排交给 LLM 做语义差异；不可用时纯 CV 兜底。

## 6. 知识库与回归测试

- 新增 `knowledge/drawing_reading.md`：投影规则、盲腔/通孔判断、TYP 必建、剖视图权威、SW 中文视图名坑。
- 回归案例：`examples/mm25/`。
- 新增测试：
  - `scripts/tests/test_drawing_ingest.py`
  - `scripts/tests/test_model_view_compare.py`
  - `scripts/tests/integration_drawing.py`

## 7. 工具与文档

- MCP 工具从 14 扩展到 17。
- `capture_model_views.py` 补强：隐藏参考面、PNG 输出、去 BMP。
- `sw_features.py` 修复固化：`extrude_cut` flip 参数、`fillet` 全边支持。
- README/SKILL/TESTING 更新。

## 8. 实施顺序

| 阶段 | 内容 | 是否连 SW |
|---|---|---|
| Phase 1 | `capture_model_views.py` 完善 | 是 |
| Phase 2 | `drawing_ingest.py` + `drawing_interpret.py` + 单测 | 否 |
| Phase 3 | `model_view_compare.py` 纯 CV | 否 |
| Phase 4 | `drawing_spec` + `drawing_build` 整合 | 是 |
| Phase 5 | MCP 新工具接入 + 文档 | 否 |
| Phase 6 | `integration_drawing.py` 实机回归 | 是 |

## 9. 风险

- 识图关闭时，语义理解弱于视觉模型；程序化 CV 保证轮廓/尺寸/孔级别校验。
- 扫描图纸质量差需增强/校正。
- 复杂剖视图仍可能需要人工确认或视觉模型辅助。
