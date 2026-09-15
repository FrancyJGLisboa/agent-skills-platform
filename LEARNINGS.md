# Project learnings — agent-skills-platform

## 2026-09-15 — File-level evals and agent-run evals answer different questions; keep both runners

`scripts/run_evals.py` runs the skill's pipeline against golden cases and never starts an
agent. Caliper (`evals/caliper/*.eval.yaml`, `docs/CALIPER.md`) starts a real agent with
the skill installed and checks discovery, instruction following, and repeat consistency.
The first pilot run showed the gap immediately: `stock-analyzer` passed every file-level
eval while Claude Code read the skill, ignored its pipeline, and computed indicators itself.

**Why:** merging the two into one runner would hide which half failed (a bad
`description`, a bad body, or a bad script need different fixes), and agent runs cost
minutes and tokens per attempt, so they cannot sit on the delivery gate.

**When to apply:** agent runs stay manual and local; CI only validates spec syntax
(`caliper validate` is offline). Feed results into marketplace certification through
`scripts/caliper_evidence.py`, never by hand-writing `checks`. Results directories
(`.caliper/`) are tool caches: `content_fingerprint()` skips dot-directories so a run
cannot make `VERIFICATION.md` stale.

## When adding a new Phase-5 gate, also touch the AGENTS.md Files block and the Step-10 report template

When introducing a new Phase-5 verifier, artifact, or generated file (eval spec,
pipeline orchestrator, etc.), update **two recurring spots** in
`references/pipeline-phases.md` that are easy to miss:

- **Step 2.5** — the AGENTS.md template's `## Files` block. Tools that read
  AGENTS.md but **not** SKILL.md (Augment, Continue.dev, Zed, etc.) only see
  the file listing here. A missing entry means an incomplete view for those
  tools.
- **Step 10** — the "Report Results" template. Add a `Pass: PASSED` line for
  the new gate so the agent's final summary reflects every check it ran.

**Why:** missed on the eval feature (caught by review) and again on the
orchestration feature (caught by review — same blind spot). The obvious
touchpoints — SKILL.md output-structure block, pipeline-phases.md file-order
table, the Phase 5 checklist — were handled both times; these two are
secondary mirrors of the same information and are silently incomplete unless
you remember them.

**When to apply:** any change that adds a generated file, validator, or
Phase-5 step. Treat as a checklist item before declaring a Phase-5 feature
done. Quick grep: `grep -n "## Files\|Report Results\|Validation: PASSED" references/pipeline-phases.md`.

## 2026-07-20 — Don't gate LLM-judge behind one provider's API key

In a cross-runtime factory ("17 platforms"), the `llm-judge` grader is **not** a
bundled vendor API call. In an agentic runtime the host agent is already an LLM
under the user's subscription and grades the criteria itself, keyless — the
runner prints the criteria for exactly that handoff. A raw API key
(`ANTHROPIC_API_KEY` today) is only needed for **unattended CI** grading, where no
agent is present.

**Why:** the landing page framed a raw `ANTHROPIC_API_KEY` as the primary judge
path and the checklist as a degraded fallback. That's backwards for every agentic
runtime and provider-locks a tool that markets cross-platform support (user
review, 2026-07-20). Shipped in #23: `make_judge()` resolves keyless first —
`$EVAL_JUDGE_CMD` (any runtime's print mode) → `claude -p --model <pinned>` (Claude
Code CLI on PATH, honors the pin) → `ANTHROPIC_API_KEY` as a last-resort fallback
for CI boxes with no runtime. Never silently passes; the canary guards every path.
(An earlier note here said "keep CI Anthropic-only, YAGNI" — superseded once the
reviewer pointed out the runtime's own model makes even CI keyless.)

**When to apply:** any docs or code describing how evals/judges run. State
agent-graded-in-runtime (keyless) as primary; a raw key is CI-only; never name a
single vendor as *required* in a visible cross-platform claim. Quick grep:
`grep -rni "ANTHROPIC_API_KEY\|llm-judge" docs/ README.md references/`.
