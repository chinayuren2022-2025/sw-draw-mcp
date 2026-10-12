# -*- coding: utf-8 -*-
"""生成当前机器的 MCP 配置（WorkBuddy / Kimi / ChatGPT-Codex）。

运行：
    python configure_mcp.py

生成到 agent-configs/generated/，路径自动使用当前 Python 和仓库根目录。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "agent-configs", "generated")
MCP_PY = os.path.join(ROOT, "scripts", "mcp_server.py")
PYTHON = sys.executable.replace("/", "\\")
MCP_PY_WIN = MCP_PY.replace("/", "\\")
OUTPUT = os.path.join(ROOT, "output").replace("/", "\\")

CONFIGS = {
    "workbuddy-mcp.json": {
        "mcpServers": {
            "solidworks-draw": {
                "command": PYTHON,
                "args": ["-X", "utf8", MCP_PY_WIN],
                "env": {"SW_DRAW_OUTPUT": OUTPUT}
            }
        }
    },
    "kimi-mcp.json": {
        "mcpServers": {
            "solidworks-draw": {
                "command": PYTHON,
                "args": ["-X", "utf8", MCP_PY_WIN],
                "env": {"SW_DRAW_OUTPUT": OUTPUT}
            }
        }
    },
    "chatgpt-mcp.json": {
        "mcpServers": {
            "solidworks-draw": {
                "command": PYTHON,
                "args": ["-X", "utf8", MCP_PY_WIN],
                "env": {"SW_DRAW_OUTPUT": OUTPUT}
            }
        }
    },
}

TOML = f'''# Codex MCP 配置（复制到 ~/.codex/config.toml 或项目 .codex/config.toml）
[mcp_servers.solidworks-draw]
command = "{PYTHON}"
args = ["-X", "utf8", "{MCP_PY_WIN}"]
'''

def main():
    os.makedirs(OUT, exist_ok=True)
    for name, cfg in CONFIGS.items():
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("wrote", path)
    toml_path = os.path.join(OUT, "codex-config.toml")
    with open(toml_path, "w", encoding="utf-8") as f:
        f.write(TOML)
    print("wrote", toml_path)
    print("python:", PYTHON)
    print("mcp_server:", MCP_PY_WIN)

if __name__ == "__main__":
    main()
