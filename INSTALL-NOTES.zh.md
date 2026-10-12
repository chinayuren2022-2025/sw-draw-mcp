# sw-draw-skill 第三方 MCP —— 本机安装说明

安装日期：2026-09-02
来源：用户自行下载的两个 zip（`sw-draw-skill-deepseek harness.zip` / `sw-draw-skill-kimi.zip`）
安装路径：`C:\Users\26905\mcp\sw-draw-skill-3p`
注册名：**`sw-draw`**（用户级 `~/.claude.json`）

## 两个 zip 的关系

**MCP 服务端完全是同一个。**

| 比对项 | 结果 |
|---|---|
| `scripts/mcp_server.py` SHA256 | 两边一致（`8B15A731…`，18844 字节） |
| `scripts/` 与 `bridge/` 全部文件 | 逐字节相同 |
| 共同文件中内容有差异的 | 仅 `agent-configs/README.md` 一个 |

deepseek 包是超集，且其 `release/` 目录内本就打包了 `sw-draw-skill-kimi.zip`
（即用户下载的第二个包）。差异只在外围：deepseek 多出
`harness/deepseek_harness.py`（以 DeepSeek 为驱动模型的 agent 外壳）、
离线部署与 FastGPT 接入文档、示例模型与截图。

故只注册一个 MCP 条目，安装的是 deepseek 超集那份。

## 环境

| 项 | 值 |
|---|---|
| Python | 3.13.14（uv 托管，`.venv`，与其他 MCP 隔离） |
| 依赖 | `requirements.txt`：pywin32==311 / mcp==1.25.0 / pymupdf / Pillow |
| 工具数 | 19 |
| 启动时是否连 SW | **否**，连接发生在每次工具调用内部（懒连接） |

安装时已删除原包中的 `__pycache__`（作者机器上的 cpython-312 字节码，
本机用 3.13，留着无用）。

## 安全审查结论

通读 `scripts/mcp_server.py` 与 `scripts/sw_core.py`，并全量 grep：

- **无**网络访问（无 urllib / requests / socket）
- **无** subprocess / os.system
- **无** eval / exec
- **无** shutil.rmtree
- 仅 `capture_model_views.py` 有一处 `os.remove`，删的是自己刚生成的临时 bmp

未发现恶意行为。代码是正经的 SolidWorks 参数化建模封装。

## 使用前必须知道的三件事

### 1. 七个工具在省略 `file` 参数时直接作用于你当前打开的文档

```
annotation_create   feature_create   part_inspect   ref_geometry_create
sketch_check        sketch_create    subassembly_manage
```

它们的实现是 `file` 为空则取 `sw.ActiveDoc`。这比 SolidworksMCP-python 更危险：
那边可以只挑只读工具用，**这边是写工具本身默认落在活动文档上**。
`sketch_check(fix=True)` 会调 SW 原生 `FullyDefineSketch` 修改草图。

**用法建议**：调这些工具时始终显式传 `file` 绝对路径。

### 2. 保存时若目标文件已在 SW 中打开，会被直接关闭且不保存

`sw_core.save_as()` 在 SaveAs 前调用 `close_doc_by_path()` → `CloseDoc(title)`。
`CloseDoc` 不保存、不提示，未保存改动直接丢失。
默认输出目录是 `output/`，只要不把工作文件存到那里，风险可控。

### 3. 它会写一个 SolidWorks 持久偏好

`sw_core.new_part()` 与 `sw_assembly.py` 会设
`SetUserPreferenceToggle(111, True)`（swAlwaysUseDefaultTemplates），不还原。

**本机无影响**：安装前已快照，该项原本就是 `True`，属空操作。
基线见 `sw_prefs_baseline_v2.json`（scratchpad）。

## 已知的本机适配问题（暂不处理）

`sw_core.find_part_template()` 先读 SW 的默认模板设置，**你的该设置为空**，
于是走兜底 glob。三条兜底路径中：

| 路径 | 命中 |
|---|---|
| `C:\ProgramData\SolidWorks\SOLIDWORKS *\templates\*.prtdot` | 2 |
| `D:\FastProgram\SW2018\...`（作者机器路径） | 0 |
| `C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\...` | 0（你的装在 `SOLIDWORKS (3)`） |

第一条命中 2016 与 2018 两份，glob 按字母序取到
`SOLIDWORKS 2016\templates\gb_part.prtdot`，即**用 2016 模板建 2018 零件**。

SW 2018 能正常读取 2016 模板，故暂不处理。
刻意不去设 SW 的默认模板偏好——那正是本次部署全程在防止的
「写用户持久设置」行为。若建模确实因此失败，届时再针对性修复。

## 验证记录

| 项 | 结果 |
|---|---|
| 依赖导入 | 通过 |
| stdio 握手 + tools/list | 通过，19 工具 |
| `claude mcp list` 健康检查 | √ Connected |
| 偏好回归（含 111） | 7/7 全部原值未变 |

未调用任何工具——该服务端所有工具均会连接并操作 SolidWorks。

## 相关

原始解压件保留在 `C:\Users\26905\mcp\_staging\`（deepseek / kimi 各一份），
确认无需比对后可删。

另两个 MCP（`solidworks-mock` / `solidworks-real`）是不同项目，
见 `C:\Users\26905\mcp\SolidworksMCP-python\DEPLOYMENT-NOTES.zh.md`。
