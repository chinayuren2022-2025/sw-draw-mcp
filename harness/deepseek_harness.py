"""deepseek_harness.py — DeepSeek 驱动的 SolidWorks 插件 harness（安装即用）

用 DeepSeek API（OpenAI 兼容、支持 function calling）作为大脑，经 MCP stdio
调用本插件包 scripts/mcp_server.py 里的 SolidWorks 工具。LLM 只做意图提取与
编排，建模/检查全部由插件内 Python 确定性执行。

用法：
    set DEEPSEEK_API_KEY=sk-xxxx            :: 或写进包根目录 .env（见 .env.example）
    python harness/deepseek_harness.py "帮我画一个Φ25、f=50的平凸透镜，BK7材料"
    python harness/deepseek_harness.py      :: 不带参数进入多轮对话，exit 退出

可选环境变量：
    DEEPSEEK_API_KEY   （必填）DeepSeek API Key，https://platform.deepseek.com 申请
    DEEPSEEK_BASE_URL  （可选）默认 https://api.deepseek.com
    DEEPSEEK_MODEL     （可选）默认 deepseek-chat（支持工具调用）

依赖：只需插件自身的 requirements.txt（mcp）；HTTP 走 Python 标准库，无额外安装。
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.normpath(os.path.join(HERE, ".."))
SERVER = os.path.join(PKG_ROOT, "scripts", "mcp_server.py")
PROMPT_FILE = os.path.join(HERE, "system_prompt.md")
MAX_ROUNDS = 20


def _load_env():
    """环境变量优先；缺省时读包根目录 .env（KEY=VALUE 行）。"""
    env_file = os.path.join(PKG_ROOT, ".env")
    if os.path.isfile(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _cfg():
    _load_env()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        sys.exit("缺少 DEEPSEEK_API_KEY：set DEEPSEEK_API_KEY=sk-xxxx "
                 "或把 KEY 写进包根目录 .env（参考 .env.example）")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    return key, base, model


def _chat(key, base, model, messages, tools):
    """调 DeepSeek chat/completions（OpenAI 兼容），返回 message 对象。"""
    body = {"model": model, "messages": messages, "temperature": 0.2}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"DeepSeek API 错误 HTTP {e.code}: {detail}") from None
    if data.get("error"):
        raise RuntimeError(f"DeepSeek API 错误: {data['error']}")
    return data["choices"][0]["message"]


def _to_openai_tools(mcp_tools):
    """MCP tool 列表 → OpenAI function calling tools。"""
    out = []
    for t in mcp_tools:
        schema = t.inputSchema or {"type": "object", "properties": {}}
        out.append({"type": "function",
                    "function": {"name": t.name,
                                 "description": t.description or "",
                                 "parameters": schema}})
    return out


async def run_agent(user_prompt: str, history: list) -> str:
    """单轮任务：连接 MCP server → DeepSeek 循环调工具 → 返回最终回复。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    key, base, model = _cfg()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", SERVER],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = _to_openai_tools((await session.list_tools()).tools)

            system = ""
            if os.path.isfile(PROMPT_FILE):
                with open(PROMPT_FILE, encoding="utf-8") as f:
                    system = f.read()
            messages = ([{"role": "system", "content": system}] if system else []) \
                + history + [{"role": "user", "content": user_prompt}]

            for _ in range(MAX_ROUNDS):
                msg = _chat(key, base, model, messages, tools)
                messages.append(msg)
                calls = msg.get("tool_calls") or []
                if not calls:
                    reply = msg.get("content") or ""
                    history.append({"role": "user", "content": user_prompt})
                    history.append({"role": "assistant", "content": reply})
                    return reply
                for c in calls:
                    name = c["function"]["name"]
                    try:
                        args = json.loads(c["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    print(f"  [tool] {name}({json.dumps(args, ensure_ascii=False)[:200]})",
                          file=sys.stderr)
                    try:
                        res = await session.call_tool(name, args)
                        text = "\n".join(
                            getattr(x, "text", str(x)) for x in res.content) or "(无输出)"
                        if res.isError:
                            text = f"[工具报错] {text}"
                    except Exception as e:
                        text = f"[调用失败] {type(e).__name__}: {e}"
                    messages.append({"role": "tool",
                                     "tool_call_id": c["id"],
                                     "content": text[:12000]})
            return "（已达最大工具调用轮数，任务未收敛，请缩小需求或分步提问）"


def main():
    prompt = " ".join(sys.argv[1:]).strip()
    history: list = []
    if prompt:
        print(asyncio.run(run_agent(prompt, history)))
        return
    print("DeepSeek × SolidWorks harness 已启动（exit 退出）", file=sys.stderr)
    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("exit", "quit"):
            break
        print(asyncio.run(run_agent(line, history)))


if __name__ == "__main__":
    main()
