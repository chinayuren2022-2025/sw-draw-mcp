# -*- coding: utf-8 -*-
"""按桌面客户端分别打包 sw-draw-skill。

输出到 release/：
  sw-draw-skill-workbuddy.zip
  sw-draw-skill-kimi.zip
  sw-draw-skill-chatgpt-codex.zip
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, "release")

COMMON_ROOT_FILES = [
    "README.md",
    "SKILL.md",
    "AGENT_USAGE.md",
    "setup.bat",
    "verify_env.py",
    "configure_mcp.py",
    "requirements.txt",
    "requirements-cv.txt",
    "mcp.stdio.example.json",
    "mcp.sse.example.json",
]

COMMON_DIRS = ["scripts", "bridge", "docs", "examples", "knowledge"]

CLIENTS = {
    "workbuddy": {
        "mcp": "workbuddy-mcp.json",
        "skill": "workbuddy-skill.md",
        "display": "腾讯 WorkBuddy",
    },
    "kimi": {
        "mcp": "kimi-mcp.json",
        "skill": "kimi-skill.md",
        "display": "Kimi Work",
    },
    "chatgpt-codex": {
        "mcp": "chatgpt-mcp.json",
        "skill": "chatgpt-codex-skill.md",
        "display": "ChatGPT / Codex",
    },
}

EXCLUDE_DIR_NAMES = {"__pycache__", ".pip-deps", "generated", "release", "packaging"}
EXCLUDE_FILE_SUFFIX = {".pyc"}


def add_dir(zf, src, arc_base):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
        for f in files:
            if f.endswith(tuple(EXCLUDE_FILE_SUFFIX)):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, ROOT)
            zf.write(full, arcname=os.path.join(arc_base, rel).replace("\\", "/"))


def build_client(client, cfg):
    zip_name = f"sw-draw-skill-{client}.zip"
    zip_path = os.path.join(RELEASE, zip_name)
    os.makedirs(RELEASE, exist_ok=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in COMMON_ROOT_FILES:
            src = os.path.join(ROOT, name)
            if os.path.exists(src):
                zf.write(src, arcname=f"sw-draw-skill/{name}")

        for d in COMMON_DIRS:
            src = os.path.join(ROOT, d)
            if os.path.isdir(src):
                add_dir(zf, src, "sw-draw-skill")

        # 空 output 目录
        zf.writestr("sw-draw-skill/output/.gitkeep", "")

        # agent-configs：只放当前客户端配置 + 专属 README
        agent_dir = os.path.join(ROOT, "agent-configs")
        agent_readme = f"""# {cfg['display']} 配置

本目录包含：

- `{cfg['mcp']}`：MCP 配置（运行 configure_mcp.py 可生成当前机器实际路径）
- `{cfg['skill']}`：桌面客户端技能说明

使用前请先运行：

    python configure_mcp.py
"""
        zf.writestr("sw-draw-skill/agent-configs/README.md", agent_readme)
        for key in ("mcp", "skill"):
            fname = cfg[key]
            src = os.path.join(agent_dir, fname)
            if os.path.exists(src):
                zf.write(src, arcname=f"sw-draw-skill/agent-configs/{fname}")

        # 客户端专属接入说明
        readme = f"""# {cfg['display']} 接入说明

1. 解压到 D:\\sw-draw-skill
2. 运行 setup.bat（检测/安装 Python 与依赖）
3. 运行 python configure_mcp.py 生成当前机器的 MCP 配置
4. 在 {cfg['display']} 桌面客户端中导入：
   agent-configs/{cfg['mcp']}
5. 详细说明见 docs/桌面客户端接入说明.md
"""
        zf.writestr(f"sw-draw-skill/接入说明-{client}.md", readme)

    print("built", zip_path)


def main():
    for client, cfg in CLIENTS.items():
        build_client(client, cfg)
    print("release dir:", RELEASE)


if __name__ == "__main__":
    main()
