# sw-draw-skill — SolidWorks 绘图插件（参数化建模技能包）

能力：**自然语言 → SolidWorks 参数化建模**。支持平凸透镜、镜筒建模、
两件套装配，以及**通用零件 spec 建模**（草图图元/尺寸/关系 + 拉伸/旋转/扫描/放样/
圆角/倒角/壳/孔/阵列/镜像/参考几何/曲线/曲面等特征级 API 封装），
建模后自动草图约束自检与零件深度检查。
全部几何计算/建模由 Python 确定性执行，LLM（DeepSeek 等）只负责理解
自然语言并提取参数。

## 运行环境（硬要求）

| 项 | 要求 | 备注 |
|---|---|---|
| 操作系统 | Windows 10/11（或 Windows VM） | COM 绑定，无 Linux 路径 |
| SolidWorks | 2018 SP5 实测（v26）；其他版本需重跑 makepy 核对 | 2016/2018 方案通用 |
| Python | 3.10+（开发机为 3.14.2） | 建议独立安装，不用 SW 自带 |
| Python 包（核心） | `pywin32==311`、`mcp==1.25.0`、`pymupdf`、`Pillow` | `pip install -r requirements.txt` |
| Python 包（可选） | `opencv-python-headless`（仅 `--cv` 深度识别需要） | `pip install -r requirements-cv.txt` |
| DeepSeek API Key | 仅使用 DeepSeek harness 方式时需要 | https://platform.deepseek.com 申请 |

## 安装（执行节点，5 步）

```bat
:: 1. 解压 sw-draw-skill 到任意目录，如 D:\sw-draw-skill
:: 2. 安装依赖（核心，不含 OpenCV）
pip install -r D:\sw-draw-skill\requirements.txt
::   可选：如需 drawing_interpret / drawing_compare 的 OpenCV 深度识别
::   pip install -r D:\sw-draw-skill\requirements-cv.txt
:: 3. 首次运行生成 COM 早绑定缓存（重要，SW 版本变更后也要重跑）
python -c "from win32com.client import gencache; gencache.EnsureModule('{83A33D31-27C5-11CE-BFD4-00400513BB57}', 0, 26, 0)"
::    ※ 非 2018 版本：把 26 改成 (SW年份-2000+8)，如 2016→24、2021→29
:: 4. 启动一次 SolidWorks 确认能正常打开
:: 5. 探活自测
cd D:\sw-draw-skill\harness && python deepseek_harness.py "检查一下 SolidWorks 状态"
```

## 使用方式一：DeepSeek harness（推荐，开箱即用）

包内 `harness/deepseek_harness.py` 是一个零额外依赖的 agent 循环：
DeepSeek API（function calling）↔ 本插件 MCP server（stdio）。

```bat
:: 配置 Key（二选一）
set DEEPSEEK_API_KEY=sk-你的密钥
::   或：复制 .env.example 为 .env 并填入 Key

:: 单句任务
python D:\sw-draw-skill\harness\deepseek_harness.py "帮我画一个Φ25、f=50的平凸透镜，BK7材料"

:: 多轮对话
python D:\sw-draw-skill\harness\deepseek_harness.py
```

harness 会先 dry-run 展示推导参数请你确认，确认后建模、自检并汇报保存路径。
可选环境变量：`DEEPSEEK_BASE_URL`（默认 https://api.deepseek.com）、
`DEEPSEEK_MODEL`（默认 deepseek-chat）。

## 使用方式二：接入其他 MCP 客户端

### 本地 stdio（Kimi Code CLI / Claude Desktop / Cursor）

把 `mcp.stdio.example.json` 内容并入客户端 MCP 配置（改 python 与脚本路径），
之后自然语言即可："画一个Φ25、f=50的平凸透镜，BK7"。

### SSE 服务（Ubuntu 智能体平台 → Windows 执行节点/VM）

```bat
D:\sw-draw-skill> python scripts\mcp_server.py --transport sse --host 0.0.0.0 --port 8711
```

平台侧 MCP 配置按 `mcp.sse.example.json` 填 VM 的 IP。防火墙放行 8711。
（绘图默认 8711，审图插件默认 8710，同机共存不冲突。）

## 使用方式三：纯 CLI（无 LLM）

```bat
python scripts\build_lens.py --nl "做一个Φ25、f=50的平凸透镜，BK7"
python scripts\build_lens.py --params "{\"type\":\"plano_convex\",\"D\":25,\"f\":50,\"material\":\"BK7\"}" --dry-run
python scripts\derive_assembly.py --intent "{\"action\":\"insert\",\"insert\":\"lens.SLDPRT\",\"into\":\"barrel.SLDPRT\",\"save\":\"asm.SLDASM\"}"
:: 按工程图近似建模示例（mm25-p1-1.pdf）
python scripts\build_mm25.py
```

`build_mm25.py` 会把 `mm25-p1-1.pdf` 的零件近似模型保存到
`output/mm25_p1_1.SLDPRT`：150×60×100 长圆块、2×Ø40 贯穿孔、
中央腰形盲腔（前/后各 20mm 深）、Ø35 横向贯穿孔、R2 全圆角。
如需与图纸三视图逐视角比对，可运行：
`python scripts/capture_model_views.py`（输出到 `output/views/`）。

完整“读图→建模→回拍对比”工作流见 `docs/PLAN_drawing_workflow.md`。
新增工具：
`drawing_ingest.py` / `drawing_interpret.py` / `drawing_spec.py` / `model_view_compare.py`。
示例 spec：`examples/mm25/drawing_spec.json`。

## 并发与路径

- 内置全局执行锁：请求在单个 SW 实例上串行排队，少量并发由锁吸收。
  更高并发请部署多个执行节点，**不要**在同一 Windows 上起多个 SW 实例抢 COM。
- 文件相对路径在 `output/` 目录解析（环境变量 `SW_DRAW_OUTPUT` 可改）。

## 目录结构

```
sw-draw-skill/
├─ README.md               本文档
├─ SKILL.md                技能说明（LLM 行为约束 + 故障速查）
├─ requirements.txt        Python 核心依赖（不含 OpenCV）
├─ requirements-cv.txt     可选 OpenCV 识别依赖（默认不装）
├─ .env.example            DeepSeek Key 配置样例
├─ mcp.stdio.example.json  本地 stdio 客户端配置样例
├─ mcp.sse.example.json    远端 SSE 客户端配置样例
├─ harness/
│  ├─ deepseek_harness.py  DeepSeek agent 循环（安装即用）
│  └─ system_prompt.md     绘图助手系统提示（可自行修改）
├─ knowledge/              光学公式/材料知识库（optics.py 的可执行依据）
├─ bridge/                 WSL→PowerShell 7→Windows Python 实机桥接脚本
│  ├─ sw_bridge_probe.py / run_sw_bridge_probe.ps1   链路探活
│  ├─ launch_sw.py / run_launch_sw.ps1               启动并等待 SW 就绪
│  ├─ cleanup_sw.ps1                                 清理测试用 SW/Python 进程
│  └─ run_integration.ps1 / run_adv_part.ps1 / run_asm.ps1   三套实机测试
├─ docs/                   文档与实机报告
│  ├─ TESTING.md           测试说明与已知边界
│  ├─ PLAN_drawing_workflow.md  读图建模工作流方案
│  ├─ 功能与用途总结.md        插件功能与用途总览
│  ├─ 缺失与未完成功能清单.md  未完成功能明细
│  ├─ 零件功能补全清单_*.md
│  ├─ 装配体功能审查清单_*.md
│  └─ reports/             integration/adv_part/asm 实机 JSON 报告
├─ examples/               零件 spec 示例（flange/shaft/spring）
├─ output/                 生成的 SLDPRT/SLDASM 输出目录
└─ scripts/                全部确定性执行脚本 + MCP server
   ├─ sw_core.py           COM 通信层（连接/模板/保存/重建/TLB 自适应）
   ├─ sw_sel.py            几何属性实体选择器（面/边/顶点/特征）
   ├─ sw_sketch.py         草图层（图元/编辑/尺寸/关系/3D 草图）
   ├─ sw_features.py       特征层（实体/孔/阵列/镜像/多实体/装饰螺纹/特征树/外观）
   ├─ sw_annotate.py       DimXpert/MBD 零件尺寸标注
   ├─ sw_advanced.py       参考几何/曲线/曲面层
   ├─ sw_config.py         配置/方程式/设计表
   ├─ sw_check.py          零件深度检查（特征错误/重建/草图质量/干涉初筛）
   ├─ sw_part_dsl.py       通用零件 spec DSL（校验 + 执行）
   ├─ sw_part.py           旧版透镜/镜筒原子工具（保留兼容）
   ├─ sw_assembly.py       装配层（两件套自动装配）
   ├─ sw_assembly_full.py  装配体补全（配合/组件管理/阵列镜像/检查/装配特征）
   ├─ drawing_ingest.py    工程图解析（PDF/图片 → 视图裁剪 + 尺寸 JSON）
   ├─ drawing_interpret.py 视图理解（轮廓/圆/剖面线 + 特征假设）
   ├─ drawing_spec.py      drawing_spec 确定性建模器
   ├─ model_view_compare.py 模型视图 vs 图纸视图差异检测
   ├─ mcp_server.py        MCP server（19 工具：12 零件 + 装配 4 + 读图 3）
   └─ tests/               纯 Python 单测（WSL 可跑）+ SW2018 实机集成测试
```

## 已知限制（SW2018）

- 平凸透镜/镜筒为专用模板；通用零件请使用 `part_build` spec DSL
- 装配为两件套（concentric + distance），超出范围需显式 spec
- 特征层各 API 的 COM 签名以 SW2018 TLB v26 为准；实机已验证四套集成测试
  （基础 13 场景 / 高级零件 9 场景 / 装配体 10 场景 / 读图建模 mm25 /
  扩展功能 5 场景）。
- 高级零件 9 场景实机全部通过（0 skip）
- 换 SW 版本后必须重跑安装第 3 步的 makepy 缓存生成（sw_core 已自动按
  RevisionNumber 推导 TLB 次版本）

## 测试

完整说明见 `docs/TESTING.md`。快速入口：

```bat
:: WSL/Linux 纯 Python 单测（不连 SW）
python -m unittest discover -s D:\sw-draw-skill\scripts\tests -p "test_*.py"

:: 从 WSL 经 PowerShell 7 实机运行三套 SW2018 集成测试
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\run_launch_sw.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\run_integration.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\run_adv_part.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\run_asm.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\run_drawing.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "<sw-draw-skill>\bridge\cleanup_sw.ps1"
```
