# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to semantic versioning where practical.

## [Unreleased]

### Added
- **Caliper pilot (agent-run reliability evidence)**: two bundled example skills
  (`stock-analyzer`, `github-release-briefing-skill`) carry a Caliper spec at
  `evals/caliper/<skill>.eval.yaml` that runs a real agent with the skill installed in a
  fresh HOME, k times, with deterministic `assert:` checks, an LLM-judged `expect:`, and
  activation / silence probes. `scripts/caliper_evidence.py` converts a run into
  `team_marketplace.py certify --evidence` JSON, bound to the tested `SKILL.md` hash and
  commit, with thresholds encoded in the stored check names. CI validates spec syntax
  offline (`caliper validate`); agent runs stay local. Pruned run records live under
  `docs/verification/caliper/`. `content_fingerprint()` now ignores dot-directories so
  Caliper's `.caliper/results/` cache beside a spec cannot make `VERIFICATION.md` stale.
  See `docs/CALIPER.md`.
- **Desktop app (`desktop/`)**: a Tauri 2 + React front end for `skill_registry.py`
  with Installed, Registry, and Recycle-bin tabs and the enable / disable / update /
  uninstall / restore actions. Holds no registry logic — every action shells out to
  `skill_registry.py … --json` — so the CLI stays the single source of truth. Built
  and clippy-checked on Linux, macOS, and Windows by a separate `Desktop` workflow
  that only runs when `desktop/` changes.
- **Desktop app, Copilot-first release (0.2.0)**: the CLI ships inside the app as a
  PyInstaller sidecar, so teammates need neither Python nor a checkout; Settings takes a
  team-library Git URL that the app clones and fast-forwards on every launch (vendored
  libgit2, no `git` install needed) with an optional access token kept in the OS
  keychain; GitHub Copilot is the default install target with detected tools listed
  first; screens are named Installed / Library / Removed; a `desktop-v*` tag builds
  signed installers for macOS, Windows, and Linux and the app updates itself from the
  published release. `skill_registry.py` gains a `platforms` subcommand.
- **Desktop app 0.3.0, library hygiene**: Installed groups each skill across the tools
  it is installed for — one row per skill with a chip per tool (click to turn off/on,
  × to remove, "Add tool" to install for another) — with checkboxes and a bottom action
  bar for bulk Enable / Disable / Update / Remove, an issues banner when a skill's files
  have gone missing or its library cannot be reached (Reinstall / Forget), and an
  updates badge on the sidebar. `skill_registry.py installed --json` reports `present`.
- **Desktop app "Use it when…"**: the skill detail view leads with what
  `discovery.json` says about when a skill fires — the question it answers, example
  requests that should and should not trigger it, trigger, decisions, success measure,
  risk tier — and a verified/failed pill read from `VERIFICATION.md`.
- **Desktop app redesign**: sidebar navigation with counts, Tailwind 4 tokens for light
  and dark, Lucide icons, Sonner toasts, an enable/disable switch per installed skill
  with hover-revealed actions, native folder pickers in Settings, and a skill detail
  drawer that shows the file tree and renders `SKILL.md` (or any text file) in place.
- **Installed-skill lifecycle in `skill_registry.py`**: `install` now records what
  landed where in `~/.agent-skills/installed.json` (override with `$AGENT_SKILLS_HOME`),
  and new commands act on that record — `installed`, `update [--check]`, `enable`,
  `disable`, `uninstall`, `trash`, `restore`, `purge`. `disable` moves a skill out of
  the tool's skills directory into `~/.agent-skills/disabled/` rather than renaming it
  in place, so no tool half-loads it. `uninstall` and registry `remove` move files to
  `~/.agent-skills/trash/` with a 30-day default TTL instead of deleting. Every
  lifecycle command and `install`/`list` accept `--tag <tag>` (and `--all` where it
  applies) for bulk operations. Library hygiene borrowed from Skills Hub; the governed
  `team_marketplace.py` path is unchanged.

### Migration
- Skills created before this capability remain valid. A missing `semantic_contract`
  is interpreted as `{"applies": false}` with a migration warning. Add the explicit
  applicability decision or a complete domain-owner-approved contract before the
  skill's next release.

### Changed
- **Question-first product and marketplace positioning**: README, GitHub Pages, social
  preview, repository description, and topics now present Agent Skills Platform as both
  a skill factory and the operating system for a user-defined skill marketplace.
  Public documentation leads with the full create-to-retire lifecycle, intended users,
  decision quality, and the unattended consumer proof standard.
- **Required skill decision contract**: every validated or marketplace-admitted skill
  must define `question`, `trigger`, `decision`, `evidence`, and `success_measure` in
  `discovery.json`. Both registries persist the contract, marketplace search weights
  questions and decisions above implementation terms, and generated skill pages render
  the five fields before outcome metadata.
- **First-skill success journey**: the default conversation now uses four
  user-facing stages — Understand, Build, Check, Try — and asks users to confirm
  only the inferred workflow and success criteria. A skill is called `verified`
  only after auto-install and one safe representative run; missing credentials,
  data, or authority produce an explicit `verification-blocked` handoff instead.
  README and website onboarding now lead with a working result and a choose-your-tool
  install path, while architecture, evals, security internals, and the 17-platform
  matrix remain available through progressive disclosure.
- **Keyless, subscription-based `llm-judge` grading** (`scripts/run_evals_template.py`):
  the `--judge` path no longer requires `ANTHROPIC_API_KEY`. It now resolves a
  grader in priority order — (1) `$EVAL_JUDGE_CMD`, any runtime's print-mode
  command (e.g. `gemini -p`); (2) `claude -p --model <pinned>` when the Claude Code
  CLI is on PATH, honoring the spec's pinned judge model, keyless under the
  subscription; (3) `ANTHROPIC_API_KEY` as a last-resort direct API call for
  unattended CI with no runtime present. An explicitly requested judge run still
  never silently passes (raises if no backend resolves), and the known-bad canary
  still guards every path. Rationale: in an agentic runtime the host agent is
  already a model under the user's subscription, so pinning the grader to one
  vendor's API key contradicted the cross-platform promise. New tests cover the
  keyless `EVAL_JUDGE_CMD` path and the no-backend error; the three bundled example
  runners are re-synced from the template.

### Added
- **Resumable structured workflow interview** (`scripts/structured_interview.py`):
  users may begin with an incomplete problem and raw materials instead of a perfect
  prompt or semantic schema. The agent records inspected evidence as proposals,
  preserves competing meanings as conflicts, and asks one bounded decision at a time.
  Generation is blocked until consequential core decisions—and conditional semantic
  definitions, precedence, grain/unit, time, ambiguity, and freshness—are confirmed
  by an identified human or safely marked not applicable. The ready `interview.json`
  is preserved in generated skills and validated during marketplace admission.
- **Conditional governed semantic contracts**: data-dependent skills can carry
  human-approved, versioned definitions with scope, grain, units, ordered source
  precedence, exact dependencies, ambiguity behavior (`answer`, `ask`, or
  `refuse_unknown`), ownership, and review timing. Marketplace health reports semantic
  freshness and release checks block overdue definitions. A SHA-bound three-skill,
  four-configuration experiment runner measures reliable behavior without claiming
  causality from synthetic results.
- **Governed GitHub and GitLab Copilot team marketplace** (`scripts/team_marketplace.py`):
  schema-v2 departmental catalog, explicit schema-v1 migration, reviewed bundles,
  generated `CATALOG.md`/`CODEOWNERS`/governance guidance, pull-request and tagged
  release workflows, exact `gh skill` paths, user/project scopes, immutable pins,
  and rollback through a previous tag. Adds release-blocking validation, security,
  pipeline, eval, ownership, approval, duplicate-identity, manifest-consistency,
  path-traversal, and pre-approved shell gates. README, GitHub Pages, install docs,
  distribution guidance, and contributor instructions now describe the shipped CLI.
  `docs/TEAM_MARKETPLACE.md` provides one canonical chronological page containing
  every setup, intake, review, release, install, update, rollback, and correction command.
  A provider abstraction supplies GitHub and GitLab backends. GitLab adds generated
  CI, `glab` releases, nested/self-managed repository support, and exact-tag
  copy-based Copilot installs while preserving schema-v2 bundles and governance.
- **Model-comparison rollouts** (`scripts/run_evals_template.py`): repeatable
  `--model <id>` on `--rollout` runs the whole golden suite once per model
  under test and prints a per-model comparison table — pass/fail/error/
  regression counts, cost, wall time — answering "which model should run this
  task, and at what price" from the skill's own eval suite. Each model id
  binds the spec `run` command's optional `{model}` placeholder and is
  exported as `$EVAL_MODEL`, so pipelines pick it up via argv or env with no
  spec change required. Cost is read strictly from an optional
  `{output}.usage.json` sidecar the pipeline may write (`input_tokens`,
  `output_tokens`, `cost_usd`) and reported `n/a` when absent — never
  estimated. Model runs are experiments, not gates: they never `--promote`
  baselines and never log to `EVOLUTION.md`; exit 0 when at least one model
  passes everything. Single-model rollout results now also carry
  `model`/`cost_usd`/token/`duration_s` fields in `--json` output. Ten new
  tests; the three bundled example runners re-synced from the template.
  Phase 5 now carries an **LLM-step contract** (`references/
  phase5-orchestration.md` "LLM steps", referenced from SKILL.md step 4 and
  `references/phase2-eval-assessment.md`): generated pipeline steps that
  invoke an LLM resolve the model from `--model` argv / `$EVAL_MODEL` env with
  one pinned default, invoke keylessly first, and write the runtime-reported
  usage sidecar — so generated skills fill the cost column automatically.
- **`--mcp-audit` front door** (`references/mcp-audit.md`,
  `scripts/mcp_audit_validate.py`): point the creator at a data vendor's MCP
  server (live connection, repo, or docs) and get a feasibility map instead of
  a build — verbatim tool inventory, ranked buildable skills with per-step
  tool mappings and agent-vs-script orchestration classes, and a not-buildable
  list where every rejection names the exact missing primitive plus the
  closest existing tool. `mcp_audit.json` is gated by the new validator
  (inventory provenance, no hallucinated tool names, no vague refusals,
  script-orchestrated candidates must declare a non-MCP data path); the human
  holdout check is deliberately never validator-graded. 21 new tests.
- **Phase 0 spec-ideation front door** (`references/spec-ideation.md`): a
  pre-Discovery step for when the user arrives without a skill in mind — one word
  ("freight"), a shrug, "give me a skill idea", or a dumped transcript with no
  goal. Instead of guessing a skill and building it, the factory harvests the
  user's *real recurring work* (never invents chores), filters to what it can
  actually ship (repeatable + markdown/scripts + data-centric + binary-checkable —
  drops apps/games/firmware), and shapes the chosen chore into the workflow Phase 1
  needs. Carries an inverted anti-slop rule (the best skill is the boring, repeated
  chore, not the clever one) and a held-out bellwether: a spec is only proven when
  the skill it produces passes its own first bundled eval. Validated end-to-end —
  an emitted spec built a skill that passed 5/5 checks, VALID, and CLEAN.
- **Cross-runtime native install manifests + README install matrix**: the repo
  now ships `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json`
  (Codex CLI), `.github/plugin/{plugin,marketplace}.json` (Copilot CLI),
  `gemini-extension.json` with `AGENTS.md` as context (Gemini CLI /
  Antigravity), and `.cursor-plugin/{plugin,marketplace}.json` (Cursor
  in-editor `/add-plugin`) alongside the existing `.claude-plugin/` pair. The
  README's Advanced Install section documents the exact in-tool install
  command per runtime, per each runtime's official plugin docs, with the
  universal installer as the honest fallback for runtimes without a native
  install verb (opencode, Goose, and the rest). A root `AGENTS.md` companion
  file joins the repo (the factory's own checklist has required one of
  generated skills all along).

### Fixed
- **skill_document.py depth-blind YAML lookups**: `field()`/`has_field()` matched
  nested keys as top-level and `subfield()` matched any depth under the parent —
  so a `dependencies[].version` could shadow `metadata.version` (mislabeling
  export zips and registry entries) and a nested `license` silenced validate.py's
  missing-license warning. All four lookups are now depth-aware; blank lines no
  longer terminate a block scan. `export_utils.get_skill_version` now reads
  `metadata.version` (it only ever worked via the old bug).
- **skill_registry.py path traversal**: `metadata.author: ".."` slugged to `..`,
  letting `cmd_publish` `rmtree` the registry's entire `skills/` root. Slugs now
  strip edge dots, and publish refuses any destination that resolves outside
  `skills/` (defense in depth).
- **dependency_health.py / schema_drift.py dead status branches**: `urlopen`
  raises `HTTPError` (a `URLError` subclass) on 4xx/5xx, so every error status
  was misreported as "unreachable". `HTTPError` is now caught first and
  classified by status code.
- **export_utils.py egg-info exclusion**: `'*.egg-info'` was exact-matched, never
  globbed, so real `.egg-info/` build metadata shipped inside export zips.

### Added
- **Pinned LLM-judge harness** (`run_evals.py --rollout --judge`): grades
  `llm-judge` criteria via the Anthropic API (stdlib urllib, `ANTHROPIC_API_KEY`)
  with the judge model + temperature pinned in the spec's `judge` block. The
  judge sees only criterion + output, and a known-bad `canary` output must fail
  every judge criterion or the entire run is invalid — a judge that passes
  garbage proves nothing. Previously llm-judge checks were printed as a
  checklist and never graded anywhere.
- **Evidence artifacts**: any failed eval run appends the raw failing check
  rows to the skill's `EVOLUTION.md` (timestamped), and
  `staleness_check --record` does the same for stale/degraded findings — a
  detected failure now produces consumable evidence, not just an exit code.
- **Shipped evolve loop**: generated skills carry `scripts/evolve.py` plus the
  staleness/dependency-health/schema-drift modules, so
  `python3 scripts/evolve.py` closes detect → record → re-verify from the
  skill's own root (previously these tools lived only in the creator repo).
  The bundled examples ship it and CI runs it end-to-end.
- **Instruction-body injection scanning** in `security_scan.py`: SKILL.md and
  reference prose are now scanned for override phrases, concealment and
  exfiltration directives, hidden/bidirectional unicode, and encoded blobs —
  skill-file prompt injection fires at load time, before any code runs, and the
  old scanner missed that class entirely. Plus a least-privilege cross-check:
  script URLs must be declared in frontmatter (`Undeclared network endpoint`).
- **Registry scan gate hardened**: `publish --force` no longer bypasses
  high-severity security findings — `--force` only overrides duplicate-version
  entries. Unreviewed ingestion is the documented dominant registry risk.
- **Real regression gate in the bundled eval runner** (`run_evals.py --rollout`):
  each produced output is now compared against the case's promoted `expected`
  baseline (JSON-value equality; `compare_ignore: [keys]` for volatile fields
  like timestamps, `compare: "none"` to opt out) — divergence that slips past
  the command checks is reported as a `<baseline>` regression and exits 1.
  Promoted baselines at `golden/<id>/expected.json` arm the gate automatically
  and are never overwritten by a later `--promote`. Previously baselines were
  write-only and behavioral regressions were undetectable.
- **Holdout split**: golden cases marked `"split": "test"` are skipped by
  default, never promoted, and scored only with `--include-holdout` (CI does
  this as release scoring). The three bundled example skills each carry a
  promoted baseline set and one holdout case.
- **Claude Code plugin install path** (ponytail-style): `.claude-plugin/plugin.json`
  + `marketplace.json` at the repo root make the factory installable with
  `/plugin marketplace add FrancyJGLisboa/agent-skills-platform` +
  `/plugin install agent-skills-platform@agent-skills-platform` — no `curl | sh`
  needed on Claude Code. Generated skills get the same treatment: Phase 5
  Step 6.5 emits manifests from `scripts/claude-plugin-template/` (placeholders
  filled from SKILL.md frontmatter), so every generated skill is installable via
  `/plugin marketplace add <repo-or-local-path>`. The root SKILL.md is discovered
  through Claude Code's root-fallback, so no restructuring into `skills/` is
  required. Export zips (Desktop/Web, API variants) still exclude
  `.claude-plugin/` — those platforms don't read it; the plugin path travels
  with the git repo or local directory instead.

### Changed
- `references/agentdb-integration.md` is now explicitly marked **DESIGN
  DOCUMENT — NOT IMPLEMENTED** (no bridge module, nightly learner, or reflexion
  storage exists), and SKILL.md/README no longer present AgentDB as a current
  learning system. The shipped learning loop is the eval harness (rollout +
  baseline promotion + regression gate + holdout).
- **Launch-readiness pass:** rewritten README first screen (working hero visual,
  quickstart, "why this vs alternatives" table), `assets/hero.svg` +
  `assets/demo.cast` terminal demo, GitHub Actions CI (`/.github/workflows/ci.yml`)
  with a status badge, issue/PR templates, `CITATION.cff`, two new runnable example
  skills (`weekly-crm-report`, `pr-blocker-summarizer`), and a launch kit
  (`LAUNCH.md` + `docs/launch/`). Corrected the platform count to the real **17**
  (was overstated as "20+") throughout the README.
- End-to-end eval **rollout harness**: `run_evals.py --rollout` runs a skill's
  declared `run` command on each golden input and scores the real output through
  the existing command checks (closing the "does not run the skill itself" gap).
  `--promote` captures the first passing output as the `pending-first-green`
  baseline; `--timeout` bounds each run. The bundled `stock-analyzer` example now
  ships a real eval spec + `run_pipeline.py` so the harness is integration-tested.
- `LICENSE` (MIT), `CONTRIBUTING.md`, and this `CHANGELOG.md`.
- Windows installers tracked in version control (`install.ps1`,
  `scripts/bootstrap.ps1`, `scripts/bootstrap.bat`, `scripts/install-skill.ps1`,
  `scripts/install-template.ps1`), with `test_install_parity.py` gating
  bash/PowerShell parity.
- Phase 5 harness patterns: every generated skill gets input validation,
  `--check-prereqs`, `--diagnostics`, self-bootstrapping wrappers, and
  `activation`/`provenance` frontmatter checks in `validate.py`.

### Changed
- Consolidated SKILL.md parsing into `scripts/skill_document.py` and the
  install-target registry into `scripts/platforms.py`.
- Bumped `architecture-guide.md` and `export-guide.md` headers to v6.0.

### Removed
- Marketing collateral (`Dynamous/`) and a one-off research dump
  (`agentic-tool-skill-systems/`).

## [6.0.0]

- Five-phase generation pipeline (discovery, design, architecture, detection,
  implementation) documented in `references/pipeline-phases.md`.
- Cross-platform export across 17 agent platforms.
- Per-skill eval specs (`evals/*.eval.md` + `scripts/run_evals.py`).
- Deterministic pipeline orchestration (`run_pipeline.py`) for multi-script
  skills.
