"""Diagnostic: drive the MCP server with a local Ollama model.

Ollama does not speak MCP. This bridges the two -- MCP client on one side, an
Ollama chat loop on the other:

    MCP list_tools -> Ollama tool format -> model picks a call
                   -> MCP call_tool -> result -> model's final answer

It prints the three stages separately -- the arguments the model chose, what
the tool returned, and how the model phrased it. That separation is the point:
a model can call the tool correctly and still misreport the result, and only a
per-stage trace tells those apart. Use novel parameters when checking for that,
since a textbook example the model may have memorised proves nothing.

    python ollama_bridge.py <model> [--python PATH] [--ask "question"]

<model> is an Ollama model that supports tools (`ollama show <m>` lists
capabilities -- though a `tools` capability is a claim, not a guarantee).
--python is the interpreter used to spawn the server; it needs `mcp`
installed, so it defaults to this repo's .venv.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/api/chat"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PYTHON = os.path.join(HERE, ".venv", "bin", "python")
DEFAULT_QUESTION = (
    "I have $10,000 saved. If I invest it at a 7% annual return and add $500 "
    "every month, what will it be worth in 30 years?"
)


def _post(payload, timeout):
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def ollama_chat(model, messages, tools=None, timeout=900):
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    # Thinking models (qwen3, qwen3.5) otherwise spend the whole budget
    # reasoning and never reach the tool call. Retry bare if the field is
    # rejected by a model that has no thinking mode.
    payload["think"] = False
    try:
        body = _post(payload, timeout)
    except Exception:
        payload.pop("think")
        body = _post(payload, timeout)
    if "error" in body:
        payload.pop("think", None)
        body = _post(payload, timeout)
        if "error" in body:
            sys.exit(f"ollama error: {body['error']}")
    return body["message"]


JUDGE = """Question a user asked: {q}

A tool was called with these arguments: {a}

Do those arguments faithfully represent the question? A percentage in the
question must appear as a decimal in the arguments (5.18% -> 0.0518).
Do NOT check any arithmetic; judge only whether the arguments match the question.
Reply with exactly PASS or FAIL, then one short reason."""


def judge(model, question, args, timeout):
    """Second opinion on intent -> arguments. Fresh context, no tools."""
    reply = ollama_chat(
        model,
        [{"role": "user", "content": JUDGE.format(q=question, a=json.dumps(args))}],
        timeout=timeout,
    )
    text = (reply.get("content") or "").strip()
    # First verdict word wins. Substring-anywhere matching mis-scored replies
    # like "not a FAIL, so PASS" -- models mention the other word while reasoning.
    m = re.search(r"\b(PASS|FAIL)\b", text.upper())
    verdict = m.group(1) if m else "?"
    return f"{verdict} ({model}): {text.splitlines()[-1][:120] if text else 'no reply'}"


async def run(model, server_python, question, timeout, verifier=None):
    params = StdioServerParameters(
        command=server_python, args=["retirement.py", "--serve-mcp"], cwd=HERE
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in listed.tools
            ]
            print(f"[mcp]    discovered: {[t.name for t in listed.tools]}")

            messages = [{"role": "user", "content": question}]
            reply = ollama_chat(model, messages, tools, timeout)
            calls = reply.get("tool_calls") or []
            if not calls:
                print("[ollama] no tool_calls -- answered from its own head:")
                print((reply.get("content") or "")[:500])
                return 1

            messages.append(reply)
            for call in calls:
                fn = call["function"]
                args = fn["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                print(f"[ollama] wants {fn['name']}({args})")
                if verifier:
                    verdict = judge(verifier, question, args, timeout)
                    print(f"[verify] {verdict}")
                result = await session.call_tool(fn["name"], args)
                text = result.content[0].text
                print(f"[mcp]    returned: {text}")
                messages.append({"role": "tool", "content": text})

            final = ollama_chat(model, messages, timeout=timeout)
            print(f"[ollama] final: {(final.get('content') or '').strip()[:800]}")
            return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("model", help="Ollama model that supports tool calling")
    p.add_argument("--python", default=DEFAULT_PYTHON, help="interpreter with `mcp`")
    p.add_argument("--ask", default=DEFAULT_QUESTION, help="question to send")
    p.add_argument("--timeout", type=int, default=900, help="per-request seconds")
    p.add_argument("--verify", metavar="MODEL", help="second model to judge the arguments")
    args = p.parse_args()
    if not os.path.exists(args.python):
        sys.exit(f"no interpreter at {args.python} -- run: pip install -e '.[mcp]'")
    sys.exit(
        asyncio.run(run(args.model, args.python, args.ask, args.timeout, args.verify))
    )


if __name__ == "__main__":
    main()
