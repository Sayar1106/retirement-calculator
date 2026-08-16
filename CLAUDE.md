# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single compound-interest projection, wrapped so any LLM agent harness can call it. Everything
lives in `retirement.py`:

```
python3 retirement.py --initial-capital 10000 --annual-return-rate 0.07 \
    --monthly-contribution 500 --years 30      # {"future_value": 691150.47}
python3 retirement.py --schema openai          # tool definition on stdout
python3 retirement.py --serve-mcp              # MCP server over stdio
```

The CLI and `--schema` paths are stdlib-only, so any harness with a shell tool can use them with
nothing installed. `--serve-mcp` is the sole dependency, declared as an optional extra and imported
lazily inside `_serve_mcp()` so the other paths keep working without it:

```
pip install -e ".[mcp]"     # only needed for --serve-mcp
```

The pin is `mcp>=2,<3` and it is load-bearing: the API moved in 2.0, where
`mcp.server.fastmcp.FastMCP` became `mcp.server.mcpserver.MCPServer`, so `_serve_mcp()` fails to
import on 1.x. Re-check that import before widening the pin.

There is no test framework.

## ollama_bridge.py — verifying a model actually relays the result

`ollama_bridge.py` drives the MCP server with a local Ollama model and prints three stages
separately: the arguments the model chose, what the tool returned, and how the model phrased it.

```
./.venv/bin/python ollama_bridge.py qwen3:0.6b --ask "..."
```

Keep it, because the obvious checks miss the failure it caught. Running under OpenClaw,
`qwen3:0.6b` called the tool with correct arguments and reported `$96,418.81` for a result of
`$99,957.78` — three times running, while OpenClaw's telemetry showed `calls: 1, failures: 0`.
The call really did succeed; the model corrupted the number afterwards, apparently under context
load (28 tool schemas and ~29k input tokens, versus one tool in the bridge, where the same model
reports correctly).

Two lessons that generalise: `failures: 0` confirms the tool ran, not that the answer survived
to the user; and always verify with **novel** parameters, since a model can produce a textbook
example like 10000/7%/500/30y from memory whether or not it read the tool's output.

## PARAMS is the source of truth

`PARAMS` and `DESCRIPTION` at the top of the file feed all four consumers: the argparse flags, the
three exported schema dialects, and the MCP tool. Adding or renaming a parameter means editing
`PARAMS` and `future_value()`'s signature together — nothing else should hardcode the parameter list.

Two consequences worth knowing before editing:

- **The MCP path mutates `future_value.__annotations__`.** The MCP SDK derives its schema from the
  function signature and exposes no override, so `_serve_mcp()` rewrites the annotations with
  `Annotated[float, Field(description=...)]` from `PARAMS`. Without it the model sees bare numbers
  with no guidance. If a parameter stops being a `float`, that dict comprehension needs updating too.
- **Dialects differ in more than key names.** Anthropic uses `input_schema` with top-level `strict`;
  OpenAI nests both under `{"type": "function", "function": {...}}`; Gemini takes an OpenAPI subset
  with uppercase type names and *rejects* `additionalProperties`. `_body(json_schema=False)` handles
  the Gemini case — don't collapse the branches.

## Financial conventions

Changing either of these silently changes every number the tool returns, so they belong in the
docstring and the `PARAMS` descriptions whenever they move:

- Compounding is **monthly** — the annual rate is divided by 12, never converted geometrically.
- Contributions are made at the **end** of each month (ordinary annuity), so the first one earns
  no return in the month it's made.
- `annual_return_rate` is a decimal (`0.07`), not a percentage (`7`).

The zero-rate case is branched separately because the annuity formula divides by the rate.
