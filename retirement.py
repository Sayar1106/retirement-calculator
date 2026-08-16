"""Future value of a retirement account, callable by any LLM agent harness.

Three wrappers, one source of truth (PARAMS):

    python3 retirement.py --initial-capital 10000 --annual-return-rate 0.07 \
        --monthly-contribution 500 --years 30      # -> {"future_value": 691150.47}
    python3 retirement.py --schema openai          # -> tool definition, stdout
    python3 retirement.py --serve-mcp              # -> MCP server over stdio
"""

import argparse
import json
import sys

# Source of truth: every wrapper below is generated from this.
PARAMS = [
    ("initial_capital", "Starting balance, in the user's currency."),
    ("annual_return_rate", "Expected annual return as a decimal, e.g. 0.07 for 7%."),
    ("monthly_contribution", "Amount added at the end of every month."),
    ("years", "Number of years the money stays invested."),
]

DESCRIPTION = (
    "Project the future balance of a retirement account, assuming monthly "
    "compounding and contributions at the end of each month. Call this when "
    "the user asks how much an investment will be worth after some number of "
    "years, or how much their savings will grow."
)


def future_value(
    initial_capital: float,
    annual_return_rate: float,
    monthly_contribution: float,
    years: float,
) -> float:
    """Project the balance of an investment account.

    Assumes monthly compounding and contributions made at the end of each month.

    Args:
        initial_capital: Starting balance.
        annual_return_rate: Expected annual return, as a decimal (0.07 = 7%).
        monthly_contribution: Amount added at the end of every month.
        years: Number of years invested.

    Returns:
        The projected balance at the end of the period.
    """
    # A rate above 1.0 means a percentage was passed instead of a decimal
    # (7 for 7%). It is the one silent failure models actually make here:
    # schema-valid, and it returns an absurd number instead of erroring.
    if not 0 <= annual_return_rate <= 1:
        raise ValueError(
            f"annual_return_rate must be a decimal between 0 and 1, got "
            f"{annual_return_rate} (for {annual_return_rate}%, pass "
            f"{annual_return_rate / 100})"
        )
    r = annual_return_rate / 12
    n = round(years * 12)
    if r == 0:
        return initial_capital + monthly_contribution * n
    growth = (1 + r) ** n
    return initial_capital * growth + monthly_contribution * (growth - 1) / r


def projection(
    initial_capital: float,
    annual_return_rate: float,
    monthly_contribution: float,
    years: float,
) -> dict:
    """future_value plus the figures a model would otherwise compute itself.

    Models reliably relay a number the tool returns, and reliably get wrong any
    number they derive themselves -- observed fabricating total contributions by
    ~$900 while the headline was exact. Returning them removes the opportunity.
    """
    fv = future_value(
        initial_capital, annual_return_rate, monthly_contribution, years
    )
    contributed = monthly_contribution * 12 * round(years)
    return {
        "future_value": round(fv, 2),
        "initial_capital": initial_capital,
        "monthly_contributions_total": round(contributed, 2),
        "growth": round(fv - initial_capital - contributed, 2),
    }


def _body(json_schema=True):
    """The parameter schema every dialect wraps."""
    type_name = "number" if json_schema else "NUMBER"
    schema = {
        "type": "object" if json_schema else "OBJECT",
        "properties": {
            name: {"type": type_name, "description": desc} for name, desc in PARAMS
        },
        "required": [name for name, _ in PARAMS],
    }
    if json_schema:
        # Required by Anthropic/OpenAI strict mode; rejected by Gemini.
        schema["additionalProperties"] = False
    return schema


def tool_schema(dialect="anthropic"):
    """Emit the tool definition in a provider's dialect."""
    if dialect == "anthropic":
        return {
            "name": "future_value",
            "description": DESCRIPTION,
            "strict": True,
            "input_schema": _body(),
        }
    if dialect == "openai":
        return {
            "type": "function",
            "function": {
                "name": "future_value",
                "description": DESCRIPTION,
                "strict": True,
                "parameters": _body(),
            },
        }
    if dialect == "gemini":
        # Gemini takes an OpenAPI subset: uppercase types, no additionalProperties.
        return {
            "name": "future_value",
            "description": DESCRIPTION,
            "parameters": _body(json_schema=False),
        }
    raise ValueError(f"unknown dialect: {dialect}")


# Kept for direct `from retirement import TOOL` use with the Anthropic SDK.
TOOL = tool_schema("anthropic")


def _serve_mcp():
    """Run as an MCP server over stdio. Requires the optional `mcp` package."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        # Report the underlying error; a broken install is not a missing one.
        sys.exit(f"--serve-mcp needs the MCP SDK (pip install mcp): {exc}")
    from typing import Annotated

    from pydantic import Field  # transitive dependency of `mcp`

    # The SDK derives the tool schema from the signature and offers no override,
    # so push the PARAMS descriptions onto the annotations before registering --
    # otherwise the model sees bare types with no guidance. Confined to this
    # process; the CLI and schema paths never run it.
    projection.__annotations__ = {
        name: Annotated[float, Field(description=desc)] for name, desc in PARAMS
    } | {"return": dict}

    server = MCPServer("retirement")
    # Tool name stays future_value -- harnesses are configured against it.
    server.tool(name="future_value", description=DESCRIPTION)(projection)
    server.run(transport="stdio")


def main(argv=None):
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--schema", choices=["anthropic", "openai", "gemini"])
    parser.add_argument("--serve-mcp", action="store_true")
    for name, desc in PARAMS:
        parser.add_argument(f"--{name.replace('_', '-')}", type=float, help=desc)
    args = parser.parse_args(argv)

    if args.serve_mcp:
        return _serve_mcp()
    if args.schema:
        print(json.dumps(tool_schema(args.schema), indent=2))
        return

    values = {name: getattr(args, name) for name, _ in PARAMS}
    missing = [n for n, v in values.items() if v is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    print(json.dumps(projection(**values)))


if __name__ == "__main__":
    main()
