---
name: agent-tool-verification
description: "Wire a tool for LLM agents to call (MCP/CLI/schema) and prove it actually works end to end. Use when building or debugging a tool an agent calls, when a harness reports success but answers look wrong, or when choosing a model for tool calling."
---

# Agent tool verification

Every rule here came from an observed failure, not from theory. The costly ones
are marked. Structural success and correct answers are different things: an agent
can call your tool, receive the right number, and still report a wrong one.

## Build

**One source of truth, three interfaces.** Keep the parameter list in one place
and generate the CLI flags, the exported schema, and the MCP tool from it. They
cannot drift, and any harness can reach at least one: CLI for anything with a
shell, schema export for hand-wired loops, MCP for clients that discover tools.

**Not every harness accepts every transport.** Check before designing. OpenClaw
takes stdio MCP servers; NVIDIA NemoClaw's managed layer rejects stdio outright
and requires remote HTTPS with bearer auth. A stdio server is unusable there no
matter how it is configured.

**Validate at the trust boundary, and make the error instructive.** State the
correction, not just the rejection:

    annual_return_rate must be a decimal between 0 and 1, got 5.18
    (for 5.18%, pass 0.0518)

This closes the loop. Given that message, a model retried and converged on the
right call with no retry logic anywhere in the code. An error saying only
"invalid input" cannot do that.

**Return every figure the model would otherwise derive.** Models relay what you
give them and mis-derive what they compute. One fabricated a contributions total
of $81,024 against a true $80,136 while reporting the headline exactly right.
Returning the breakdown removed the opportunity rather than detecting the result.

**Field names are prompt text.** `total_contributions` was ambiguous about
whether initial capital was included; a model relayed it correctly and then
invented a decomposition to reconcile its own misreading. Renaming it
`monthly_contributions_total` fixed that. Name fields so a reader with no schema
cannot misread them.

## Verify

**Never trust structural telemetry.** A harness reporting `failures: 0` means
neither that the answer survived nor that the tool succeeded — tool results
flagged `is_error` were not counted as failures. Use it to confirm a call
happened; never to confirm correctness.

**Always use novel parameters.** This is the one that matters most. A textbook
case (10000 / 7% / 500 / 30y) passed while the same model was corrupting results
on unfamiliar numbers, because it can produce a memorised answer whether or not
it read the tool's output. Random, awkward values: four-decimal rates, non-round
amounts, odd horizons. Include the edge cases that exercise separate code paths
(a zero rate, a zero contribution).

**Never name the tool in the prompt.** "Use the retirement tool" tests plumbing.
A plain question tests whether the model selects it unprompted, which is what
production looks like.

**Trace per stage.** Arguments, tool return, and final prose are three
independent failure points, and a single pass/fail cannot tell them apart:

    [agent] wants  fn({rate: 0.043, years: 19, ...})   <- extraction correct?
    [tool]  returns 99957.7789                          <- computation correct?
    [agent] final  "approximately $96,418.81"           <- relay correct?

That third line is a real observed failure: correct arguments, correct return,
fabricated answer, reproducible three times, with telemetry reporting success
throughout. Without the per-stage split it looks like a broken tool.

**Verify deterministically; do not use an LLM judge.** The answer is data, so
comparison is arithmetic. Given the parameters, every legitimate figure is
computable, and any number in the reply matching none of them is fabricated.
Measured alternative: an LLM judge scored 50% false positives on correct
arguments and missed 25% of the subtle failures. It reliably caught only blatant
errors. A judge is defensible for non-numeric claims; nothing else.

**Check the whole answer, not the headline.** A reply can quote the tool's number
exactly and surround it with invented supporting figures.

**Check digit grouping separately.** `$6,911,50.47` normalises to the correct
value once commas are stripped, so a value comparison passes it, while a reader
sees ten times the real number.

**Test the test.** Break the implementation deliberately and confirm the check
fails. A differential test that never fails is decoration. Independent
reimplementation is the standard: a naive month-by-month loop caught what a
closed-form formula checked against itself never could.

## Choosing and configuring a model

**A declared capability is a claim, not a guarantee.** A model advertising
`tools` support answered in prose instead, and its arithmetic was wrong by
$52,000. Test before trusting.

**Context load determines reliability more than you expect.** Same model, same
question, varying only the number of tools in context:

| Tools in context | Correct |
|---|---|
| 28 | 0/3 |
| 6 | 5/7 |
| 2 (with a larger model) | 3/3 |

Cut the tool set to what the task needs. Scope it per provider or per agent so
trimming one path does not strip capability from the rest.

**Context also dominates latency.** A large model timed out repeatedly on
prompt processing with 22k characters of tool schemas; the same model answered
in 20-90s once that was cut to ~700. Suspect context before blaming the model.

**Watch for auxiliary tools as decoys.** An MCP server exposes `prompts_get`,
`prompts_list`, `resources_list` and `resources_read` alongside yours. A model
picked one of those and gave up. Allowlist the exact tool name.

**Thinking modes can starve the tool call.** Reasoning models spent their entire
budget thinking and never reached the call. Disable thinking for tool-calling
runs unless you have measured that it helps.

## Order of work

Cheapest first; each answers a different question.

1. **Is the tool's math right?** Differential test against an independent
   implementation. No model involved, milliseconds.
2. **Does the agent relay it?** Randomised parameters, ground truth computed
   directly from the tool, compare against the reply. One comparison catches a
   missing call, wrong arguments, and a corrupted relay alike, because all three
   produce a mismatched number.
3. **Which stage broke?** Per-stage trace, only when step 2 fails.

Step 1 failing means your code. Step 1 passing and step 2 failing means the
model. Run several trials: small models are inconsistent, and a single pass is
not a result.

## Known gaps worth stating

A fixed prompt template tests numeric robustness, not phrasing robustness.
Varying the wording at fixed numbers is a different test, and usually the
untested one.
