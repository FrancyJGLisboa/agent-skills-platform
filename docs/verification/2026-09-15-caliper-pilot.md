# Caliper pilot — agent-run reliability evidence

Run date: 2026-09-15. Tool: `caliper-eval` 0.11.0. Agents: Claude Code 2.1.272, Codex CLI
0.154.0, each judged by the other vendor. k=3, `--workers 1`, `--timeout 180`, on one
macOS laptop. Pruned run records (no transcripts, no agent output, no file contents) are in
`docs/verification/caliper/<skill>/`. These are agent-run technical emulations; they are
not evidence of human adoption or business correctness.

## What was measured

Two bundled example skills, each with three tasks: a happy path, an edge case, and a
silence probe (`activates: []`). Every task asserts which skill must load.

| Skill | Agent | Happy path | Edge case | Activation | Unusable | Adapter verdict |
|---|---|---|---|---|---|---|
| github-release-briefing-skill | claude-code | 3/3 | 3/3 | 100% | 0 | certifies |
| github-release-briefing-skill | codex | 1/3 | 3/3 | 100% | 0 | refused |
| stock-analyzer | claude-code | 0/3 | 2/2 (+1 timeout) | 100% | 2 | refused |
| stock-analyzer | codex | 0/3 | 0/3 | 100% | 0 | refused |
| stock-analyzer, skill ablated | claude-code | 0/3 | 0/3 | n/a | 0 | n/a (baseline) |

## Findings

1. **Activation works on both runtimes.** Both agents loaded the right skill on every
   relevant prompt and neither loaded it for the haiku. The file-level routing tests in
   `discovery.json` could not have shown this.
2. **`stock-analyzer` is followed for its rules but not for its pipeline.** On every
   attempt, both agents read the skill, noticed that `scripts/main.py` returns hardcoded
   mock values, and computed RSI/MACD themselves from a live market source instead of
   running the bundled script. Claude Code said so explicitly. The skill's SKILL.md is a
   specification document, not an operating instruction; nothing in it tells the agent
   the pipeline is the deliverable. The file-level evals pass because they run the script
   directly. Ablation confirms the skill still adds value on the edge case (100% → 0%
   without it): the rule "report an unsupported indicator instead of inventing one" is
   followed, the pipeline is not.
3. **Format-fidelity asserts are the wrong check.** The first spec asserted the
   pipeline's exact Markdown heading; both agents re-formatted the briefing while keeping
   the tag, dates, and both URLs. The committed spec asserts substance only.
4. **Concurrent Caliper processes hang the Claude CLI.** Running two `caliper run`
   processes at once produced three 180-second timeouts with empty transcripts (one on a
   4-second haiku task). Runs made one at a time produced none. Run one process at a time.
5. **Codex improvises when the upstream API fails.** Two of three Codex happy-path
   attempts hit GitHub's unauthenticated rate limit (HTTP 403, caused by this pilot's own
   repeated runs). The skill says to state clearly when a repository is unavailable;
   Codex instead gathered the release from web search and an MCP fetch tool and wrote the
   briefing itself. The judge marked both attempts as failures for bypassing the pipeline.
   Set `GITHUB_TOKEN` before running this spec repeatedly.
6. **Your machine's configuration is visible to the agent under test.** The claude-code
   harness copies `~/.claude.json`, so the agent saw and named the operator's MCP servers.

## Adapter checks exercised

- `github-release-briefing-skill` (claude-code) → `certify` accepted in a throwaway
  marketplace; stored checks include `caliper:success_rate>=0.90(observed=1.00)`,
  `caliper:min_pass_hat_k>=0.70(observed=1.00)`, `caliper:unusable_attempts<=1(observed=0)`,
  `caliper:activation>=0.90(observed=1.00)`, `caliper:skill_sha256=91da7895e1e7`.
- `stock-analyzer` runs → refused: success rate 0.50 / 0.00, pass^k 0.00, 2 unusable.
- Ablated run → refused ("measures the agent without the skill").
- A `stock-analyzer` run presented for `github-release-briefing-skill` → refused (no
  snapshot of that skill).
- A hand-edited result (one outcome flipped to `pass`) → refused (stored score disagrees
  with attempts).

## Cost

About 60 agent attempts and 30 judge calls in total, roughly 1.8M input tokens (mostly
cache reads), ~75 minutes of wall time at one process at a time.
