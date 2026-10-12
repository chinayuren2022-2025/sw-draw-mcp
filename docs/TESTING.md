# 测试与实机验证说明

> 目标环境：Windows 10/11 + SolidWorks 2018 SP5 + Windows Python 3.14 + pywin32。
> 开发环境：WSL/Linux，只做纯 Python 单测与语法检查；COM 实机测试必须经
> `bridge/` 下的 PowerShell 7 脚本调用 Windows Python 执行。

## 1. 测试套件总览

| 套件 | 路径 | 场景数 | 最近实机结果 |
|---|---|---|---|
| 基础零件主链路 | `scripts/tests/integration_sw2018.py` | 13 | 13/13 ✅ |
| 高级零件 | `scripts/tests/integration_part_advanced.py` | 9 | 9/9 ✅（0 skip） |
| 装配体 | `scripts/tests/integration_assembly.py` | 10 | 10/10 ✅ |
| 读图建模 | `scripts/tests/integration_drawing.py` | 1 | 1/1 ✅ |
| 扩展功能 | `scripts/tests/integration_extended.py` | 5 | 5/5 ✅（subassembly dissolve 记为 skipped） |
| 纯 Python 单测 | `scripts/tests/test_*.py` | 22 | 22/22 ✅ |

实机报告保存在 `docs/reports/`：
`integration_report.json`、`adv_part_report.json`、`asm_report.json`。

## 2. WSL 侧纯 Python 单测

```bash
cd sw-draw-skill/scripts/tests
python3 -m unittest discover -s . -p "test_*.py"
```

包含：optics 参数推导、part-spec DSL 校验、草图开环/自交几何、
模块导入与 PUBLIC_API 契约检查（用 `tests/stubs/` 模拟 pywin32）。

## 3. Windows 实机测试（经 WSL→PowerShell 7→Windows Python）

先启动 SW（或让脚本自动启动）：

```bash
# 从 WSL 执行（路径按实际发行版调整）
'/mnt/c/Program Files/PowerShell/7/pwsh.exe' -NoProfile -ExecutionPolicy Bypass \
  -File '\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\bridge\run_launch_sw.ps1'
```

然后运行套件：

```bash
pwsh ... bridge/run_integration.ps1        # 基础 13 场景
pwsh ... bridge/run_adv_part.ps1           # 高级零件 9 场景
pwsh ... bridge/run_asm.ps1                # 装配体 10 场景
pwsh ... bridge/run_drawing.ps1            # 读图建模 mm25 全流程
pwsh ... bridge/run_extended.ps1          # 装饰螺纹/特征树/DimXpert/子装配体
```

单场景调试：

```bash
pwsh ... bridge/run_one.ps1 -Only patterns_mirror
pwsh ... bridge/run_one_adv.ps1 -Only multibody
pwsh ... bridge/run_asm.ps1 -Only component_state
```

清理 SW/Python 进程：

```bash
pwsh ... bridge/cleanup_sw.ps1
```

链路探活：

```bash
pwsh ... bridge/run_sw_bridge_probe.ps1
```

## 4. 装配体覆盖范围

`scripts/sw_assembly_full.py`（31 个公开函数）：
- 配合：`add_mate_full`（AddMate3/4/5 回退、距离/角度上下限、齿轮比、
  锁定旋转、定位配合）、`list_mates`/`delete_mate`/`suppress_mate`/
  `check_mates_full`
- 组件：`insert_component_full`（AddComponent4/5）、`set_component_suppression`/
  `set_component_visible`/`is_fixed`/`fix_component`/`float_component`/
  `replace_component`/`delete_component`/`move_component`/
  `insert_new_virtual_part`/`insert_new_assembly`/`save_virtual_component`
- 阵列镜像：`linear_pattern_components`/`circular_pattern_components`/
  `mirror_components`/`sketch_driven_pattern_components`/`derived_pattern_components`
- 检查：`assembly_interference`/`assembly_mass_properties`/`assembly_rebuild_report`
- 装配特征：`assembly_cut`/`hole_series`/`add_mate_reference`
- 编排：`run_spec`

MCP 工具新增：`assembly_spec_dry_run`、`assembly_build`、`drawing_ingest`、
`drawing_build`、`drawing_compare`（当前共 17 个）。

## 5. 读图建模工作流

方案见 `docs/PLAN_drawing_workflow.md`，组件：

- `scripts/drawing_ingest.py`：PDF/图片 → 视图裁剪、文本/尺寸 JSON
- `scripts/drawing_interpret.py`：轮廓/圆/特征假设
- `scripts/drawing_spec.py`：drawing_spec 确定性建模
- `scripts/model_view_compare.py`：默认只生成 side_by_side（Pillow）；`--cv` 才启用 OpenCV 边缘/圆识别
- `knowledge/drawing_reading.md`：读图规则知识库
- OpenCV 是可选依赖：默认不安装，见 `requirements-cv.txt`
- 装饰螺纹/特征树/DimXpert/子装配体见 `docs/reports/extended_report.json`
- `examples/mm25/`：mm25 回归案例（含 drawing_spec.json）

## 6. 已知边界（按需求不做）

- 钣金、焊件、装配爆炸图、完整设计表不实现；
- 边界凸台在 SW2018 无 InsertBoundaryFeature，当前使用
  InsertNetBlend2 优先、放样语义回退；
- `deform` 为占位（SW2018 无公开创建签名）。

## 7. 版本注意事项

- TLB 次版本按 RevisionNumber 自动推导（2018→26）；换 SW 版本仍需重跑
  `gencache.EnsureModule`（README 安装第 3 步）。
- 所有 COM 签名以 SW2018 SP5 实测为准；升级版本后先跑三套集成测试，
  按错误信息修正 `sw_*` 模块中的候选签名。
