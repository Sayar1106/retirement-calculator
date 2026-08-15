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

The CLI and `--schema` paths are stdlib-only. `--serve-mcp` is the sole dependency (`pip install
mcp`) and is imported lazily inside `_serve_mcp()`, so the other paths keep working without it.
There is no build step and no test framework.

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
