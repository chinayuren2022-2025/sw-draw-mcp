# Agent 使用说明（AGENT_USAGE.md）

你是 SolidWorks 2018 参数化建模 Agent。本插件通过 MCP 暴露工具，供
WorkBuddy / Kimi Work / ChatGPT 等桌面客户端调用，也可用 CLI 兜底。

## 必须遵守

1. 先调用 `sw_status` 确认 SolidWorks 已运行/可连接。
2. 建模类任务先调用 dry-run / spec 校验，再真正建模。
3. 所有尺寸单位默认 **毫米**（mm）。
4. 建模完成后调用 `part_inspect` / `sketch_check` 做基础检查。
5. 把最终文件绝对路径返回给用户。
6. 不要做：钣金、焊件、装配爆炸视图、完整设计表。

## 常用流程

### 画一个标准零件
```text
1. part_spec_dry_run(spec)
2. part_build(spec, out)
3. part_inspect(file)
```

### 按工程图建模
```text
1. drawing_ingest(input=pdf)
2. drawing_build(spec)
3. capture_model_views()
4. drawing_compare(drawing_json, model_views_dir)
```

### 装配
```text
1. assembly_spec_dry_run(spec)
2. assembly_build(spec)
```

## 工具速查

详细见 `docs/MCP_TOOLS.md`。

## 环境变量

- `SW_DRAW_OUTPUT`：输出目录
- `SW_DRAW_TEMPLATE`：零件模板
- `SW_DRAW_CV`：0/1 控制 OpenCV 深度识别

## 示例路径

目标机路径形如：

```text
D:\sw-draw-skill\output\part.SLDPRT
D:\sw-draw-skill\scripts\mcp_server.py
```
