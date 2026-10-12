# 测试说明

## 1. 纯 Python 单测（WSL/Linux 即可，不连 SolidWorks）

```bash
python3 -m unittest discover -s . -p "test_*.py"
```

覆盖：optics 参数推导、spec DSL 校验/dry-run、草图开环/自交几何算法。

## 2. SW2018 实机集成测试（必须在 Windows + SolidWorks 2018 执行节点运行）

先按 README 安装第 3 步生成 makepy 早绑定缓存，然后：

```bat
python D:\sw-draw-skill\scripts\tests\integration_sw2018.py --strict
```

- 每个场景新建零件，try/except 后继续，输出 JSON 报告；
- `--list` 列场景；`--only a,b` 只跑指定场景；
- 失败信息区分“签名不匹配 / 选择失败 / 几何失败”，据此修正
  `sw_sketch.py` / `sw_features.py` / `sw_advanced.py` 中对应函数的候选签名。

## 3. 回归基线

`legacy_lens` / `legacy_barrel` 场景保证旧模板不被重构破坏；其余场景对应
补全清单 8.2 的 P0/P1 里程碑样例。
