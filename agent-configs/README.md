# Agent 配置/技能样例

本目录存放各桌面客户端的 MCP 配置与“技能”提示词样例。

- `workbuddy-mcp.json`：WorkBuddy MCP 配置
- `kimi-mcp.json`：Kimi Work MCP 配置
- `chatgpt-mcp.json`：ChatGPT/Codex MCP 配置
- `workbuddy-skill.md`：WorkBuddy 技能说明
- `kimi-skill.md`：Kimi Work 技能说明
- `chatgpt-codex-skill.md`：ChatGPT/Codex 技能说明

核心实现不需要为每个平台重写；各平台只是通过 MCP 调用同一套 `mcp_server.py`。
