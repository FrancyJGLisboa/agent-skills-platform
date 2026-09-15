# Agent-run reliability evidence with Caliper

**Status: pilot.** Two bundled example skills carry a Caliper spec; the factory emits one
for every new skill, and `team_marketplace.py reliability` runs it per platform. Agent runs
happen on the operator's machine; CI only checks that the specs parse.

## What it adds

Every skill this factory produces ships file-level evals (`scripts/run_evals.py`): the
skill's own pipeline runs against golden cases and shell checks. Those evals never start an
agent. They cannot tell you whether an agent that has the skill installed will notice it,
follow its instructions instead of improvising, or produce the same result three times in a
row.

[Caliper](https://github.com/edonadei/caliper) (`caliper-eval`, MIT) answers those
questions. It installs the skill into the agent's normal skills folder inside a fresh
temporary HOME, runs each task `k` times, grades every attempt with a Python `assert:` and
an LLM-judged `expect:`, records which skills the agent loaded, and saves one JSON file per
run with SHA-256 hashes of the skill files it tested.

| Question | File-level evals | Caliper |
|---|---|---|
| Does the pipeline script produce the right file? | yes | yes (via `assert:`) |
| Does an agent discover the skill from its description? | no | yes (`activates:`) |
| Does the agent follow the skill instead of improvising? | no | yes (`expect:` + tool transcript) |
| Is the result consistent across repeated runs? | no | yes (`pass^k`) |
| Does the skill beat the bare agent? | no | yes (`--ablate`) |
| Does it run on more than one agent runtime? | no | yes (`--model claude-code` / `codex`) |

The pilot already produced one finding the file-level evals cannot: on `stock-analyzer`,
Claude Code read the skill, judged its mock pipeline unhelpful, computed indicators itself
against a live market source, and skipped the requested output file. That is an
instruction-following failure of the `SKILL.md`, invisible to `run_evals.py`.

## Install and run

```bash
uv tool install caliper-eval==0.11.0      # or: pipx install caliper-eval==0.11.0
caliper --help
```

Backends are CLI agents only: `claude-code`, `codex`, `pi`, `hermes`. There is no direct API
backend and no GitHub Copilot backend. The backend and judge are runtime flags, never spec
fields.

```bash
SPEC=references/examples/stock-analyzer/evals/caliper/stock-analyzer.eval.yaml
caliper validate "$SPEC"

# Iterate at k=1 until the spec itself is stable.
caliper run "$SPEC" --k 1 --timeout 180 --model claude-code --judge-model codex --verbose

# Measure. --workers 1 is required: attempts of one task run in parallel otherwise and
# the fixed /tmp work paths in the spec would collide.
caliper run "$SPEC" --k 3 --workers 1 --timeout 180 --model claude-code --judge-model codex \
  --output .caliper/runs/stock-analyzer-claude-code.json
caliper run "$SPEC" --k 3 --workers 1 --timeout 180 --model codex --judge-model claude-code \
  --output .caliper/runs/stock-analyzer-codex.json

# The real baseline: same tasks, skill removed.
caliper run "$SPEC" --k 3 --workers 1 --timeout 180 --model claude-code --judge-model codex \
  --ablate stock-analyzer --output .caliper/runs/stock-analyzer-claude-code-ablated.json
caliper compare .caliper/runs/stock-analyzer-claude-code.json \
                .caliper/runs/stock-analyzer-claude-code-ablated.json
```

Raw runs land in a `.caliper/` directory (gitignored). Pruned copies without transcripts
are committed under `docs/verification/caliper/<skill>/` as evidence.

## Spec layout

A spec lives at `<skill>/evals/caliper/<skill>.eval.yaml`. It is part of the skill's
behavior-defining files, so adding or editing one changes the verification fingerprint and
`VERIFICATION.md` must be regenerated (`python3 scripts/generate_verification.py <skill>`).

```yaml
skills:
  - ../../SKILL.md                 # the whole skill directory is installed under its frontmatter name
sandbox:
  forbidden_files:
    - "evals/"                     # golden cases are answer keys: not installed, not readable
    - "references/examples/"       # the repository checkout is a back door around the install
tasks:
  - name: Happy path
    setup: rm -rf /tmp/caliper-x && mkdir -p /tmp/caliper-x
    cleanup: rm -rf /tmp/caliper-x
    prompt: "…a request a real user would type, with absolute output paths…"
    activates: [skill-name]        # exact set of skills expected to load
    expect: "…what the judge must see in the transcript and final reply…"
    assert: |                      # deterministic; runs from the spec directory, 30 s cap
      from pathlib import Path
      assert Path("/tmp/caliper-x/out.json").exists()
  - name: Stays silent on an unrelated request
    prompt: "Write a haiku about autumn rain."
    activates: []                  # silence probe: no judge call, cheap
```

Three tasks per skill are enough for the pilot: a happy path, an edge case, and a silence
probe. Put every mechanically checkable claim in `assert:`; keep `expect:` for what only a
transcript reveals (did it run the skill's script, did it refuse to invent values).

## Operator flow: one command per skill

The marketplace operator's agent does not type the commands below by hand. It runs:

```bash
python3 scripts/team_marketplace.py reliability <skill> --department <dept> --marketplace <dir>
```

which, for every declared platform Caliper can drive and whose CLI is installed, runs the
spec, binds the run, and certifies what passes (see the
[team marketplace guide](TEAM_MARKETPLACE.md#agent-run-reliability-evidence-caliper)).
`check --release --require-reliability` then refuses a release whose `claude-code` or
`codex` certification carries no `caliper:*` checks. The creator agent's only duty is to
emit `evals/caliper/<skill>.eval.yaml` in Phase 5 from
`references/templates/caliper-eval-template.yaml`.

The rest of this page is the manual path, useful for iterating on a spec.

## From a run to marketplace certification

`scripts/caliper_evidence.py` turns a run into the evidence JSON that
`team_marketplace.py certify --evidence` already accepts:

```bash
python3 scripts/caliper_evidence.py .caliper/runs/stock-analyzer-claude-code.json \
  --skill references/examples/stock-analyzer \
  --output docs/verification/caliper/stock-analyzer/claude-code-2026-09-15.json \
  --evidence-out /tmp/stock-analyzer-claude-code-evidence.json
python3 scripts/team_marketplace.py certify stock-analyzer --department finance \
  --platform claude-code --evidence /tmp/stock-analyzer-claude-code-evidence.json \
  --marketplace ./acme-skills
```

The adapter refuses, with exit code 1, when:

- the run's `SKILL.md` hash differs from the skill on disk, or the recorded commit differs
  from `HEAD` (`--allow-git-drift` accepts the second case and records it);
- the run backend is not the platform being certified;
- stored metrics disagree with the attempt outcomes (hand-edited file);
- the run was interrupted, ablated, or scored no task;
- a threshold fails. Defaults: success rate ≥ 0.90, minimum per-task pass^k ≥ 0.70,
  unusable attempts ≤ 1, activation ≥ 0.90 when any task asserts `activates:`, and,
  with `--ablation`, success-rate delta ≥ 0.20.

Certification records store only check names, so every name carries its threshold and the
observed value, for example `caliper:success_rate>=0.90(observed=1.00)`,
`caliper:unusable_attempts<=1(observed=0)`, `caliper:model=cli-default`,
`caliper:skill_sha256=5b56aebdaaf2`. Certification is version-bound and cleared on
`update`, exactly like any other platform evidence.

## Read the numbers correctly

- **Success rate** is over usable attempts only. Timeouts, rate limits and judge errors are
  excluded from the denominator, so a skill that makes the agent loop until timeout could
  post a clean rate. Always read the unusable count next to it; the adapter caps it.
- **pass^k** (all k attempts pass) is the consistency number. An 80% rate gives ≈ 99%
  pass@3 but only ≈ 51% pass^3.
- **`--ablate`** is the only real baseline. A high rate with the skill proves little if the
  bare agent scores the same.
- **Activation** has its own scoreboard and is never blended into the success rate: a bad
  `description` and a bad body need different fixes.
- **Model** defaults to whatever the CLI resolves unless pinned with
  `--model claude-code:<model-id>`; the evidence records the resolved value.

## Limits

- **Detection, not containment.** The sandbox scans tool inputs for forbidden paths and
  marks violations as `cheat` after the fact. The agent runs on your machine, with your
  credentials and network, with permission prompts disabled. `setup`/`cleanup` are plain
  shell commands. Keep fixtures synthetic; never point a task at production data.
- **Your configuration travels.** The claude-code harness copies `~/.claude.json` and your
  credentials into the temporary HOME, so your MCP servers are visible to the agent under
  test. Hooks in `~/.claude/settings.json` and `~/.claude/skills` are not copied.
- **Cost.** One spec at k=3 on one backend is 9 agent attempts plus one judge call per
  attempt with an `expect:`. Both pilot skills on both backends plus one ablation run took
  about 45 agent attempts and roughly 40 minutes at `--workers 1`.
- **Young tool.** The spec schema moved between the published README and 0.11.0. Pin the
  version, run `caliper validate` after every upgrade (CI does), and expect the adapter to
  fail loudly on a result whose `run.era` it does not know.
- **Run one Caliper process at a time.** Two concurrent runs produced three 180-second
  timeouts with empty transcripts on the Claude CLI; sequential runs produced none.
- **Upstream rate limits become findings.** Repeated runs against a public API exhaust
  unauthenticated quotas; export the relevant token (`GITHUB_TOKEN` for the release
  skill) first, or the report measures the agent's fallback behaviour instead of the skill.
- **No Copilot backend.** Evidence for `github-copilot` still comes from the existing
  representative-run attestation, not from Caliper.
