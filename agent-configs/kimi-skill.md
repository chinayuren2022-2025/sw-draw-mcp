# Kimi Work 技能：SolidWorks 2018 参数化建模

- 用途：通过 MCP 调用本机 SolidWorks 2018 建模。
- 接入：MCP server `solidworks-draw`，stdio 或 SSE。
- 如果使用 SSE：`http://127.0.0.1:8711/sse`（仅本机）。
- 必须先调用 `sw_status`。
- 尺寸单位：毫米。
- 先 dry-run，再 build。
- 不要做：钣金、焊件、装配爆炸视图、完整设计表。
- 详细工具见 `docs/MCP_TOOLS.md`。
- 任务模板见 `docs/AGENT_TASKS.md`。
