---
name: agent-skills-platform
description: >-
  Create cross-platform agent skills from workflow descriptions. Activates when
  users ask to create an agent, automate a repetitive workflow, create a custom
  skill, or need advanced agent creation. Triggers on phrases like create agent
  for, automate workflow, create skill for, every day I have to, daily I need to,
  turn process into agent, need to automate, create a cross-platform skill,
  validate this skill, export this skill, migrate this skill, audit this skill,
  is this skill safe, vet a skill before installing, what does this skill access.
  Supports single skills, multi-agent suites, transcript processing,
  template-based creation, interactive configuration, cross-platform export,
  spec validation, and security auditing of third-party skills before install.
license: MIT
activation: /agent-skills-platform
# Compatibility alias: /agent-skill-creator
metadata:
  author: Francy J G Lisboa
  version: 6.1.0
  created: 2025-10-18
  last_reviewed: 2026-08-11
  review_interval_days: 180
  dependencies:
    - name: GitHub repository transport
      url: https://github.com/FrancyJGLisboa/agent-skills-platform
      type: service
    - name: GitHub raw bootstrap transport
      url: https://raw.githubusercontent.com/FrancyJGLisboa/agent-skills-platform/main/scripts/bootstrap.sh
      type: service
provenance:
  maintainer: Francy J G Lisboa
  version: 6.1.0
  created: 2025-10-18
  source_references:
    - https://github.com/FrancyJGLisboa/agent-skills-platform
    - https://agentskills.io
compatibility: >-
  Works on all platforms supporting the Agent Skills Open Standard (SKILL.md):
  Claude Code, GitHub Copilot CLI, VS Code Copilot, Cursor, Windsurf, Cline,
  OpenAI Codex CLI, Gemini CLI, and more — 17 platforms total.
---
# /agent-skills-platform — Turn Existing Work Into a Reusable Skill

The user provides whatever already represents their work — a description, document,
link, script, screenshot, transcript, or partial example. Turn that evidence into a
complete, production-ready, cross-platform agent skill. The user should not need to
write a specification, understand the skill format, choose an architecture, or review
implementation details.

Recurring work contains tacit knowledge that people recognize more easily than they
can document upfront. Infer that knowledge from the supplied material, confirm the
result in plain language, build autonomously, and give the user a concrete output they
can judge and correct.

## The User Journey

Use this guided-light path by default. Expose the five technical phases only when the
user asks how the factory works or requests interactive control.

1. **Understand** — read the evidence and summarize the question, trigger, supported
   decision, required evidence, and measurable success condition alongside the
   workflow, input, and output. Ask for one confirmation or correction.
2. **Build** — create the skill autonomously. Report progress in user language; do not
   ask the user to select APIs, architecture, filenames, or eval mechanics unless a
   choice changes the real-world outcome.
3. **Check** — run validation, pipeline, security, and eval gates. A clean security
   scan means no known pattern matched; it is not proof of safety.
4. **Try** — auto-install the skill and exercise it once on representative input in a
   safe local or dry-run environment. Show the output and ask whether it matches the
   user's work.

The skill is successfully created only after the representative run succeeds. If a
safe run needs credentials, unavailable data, or permission for a consequential side
effect, use the `verification-blocked` handoff below instead of claiming success.

At creation start, run `python3 scripts/success_ledger.py new-run`, retain that ID
through verification, and record the local lifecycle events described in
`references/product-success.md`. Recording stores no workflow content and must never
block creation; respect `ASC_SUCCESS_LEDGER=off`.

### First-run destination routing

Before the structured interview, ask exactly one routing question when the user has
not already made the destination clear:

> Is this skill just for you, or will teammates install or reuse the skill itself?

- **Just for me** — create, verify, and install a private skill. Do not ask the user
  to create a marketplace or invent owners and approval state.
- **My team** — ask whether a governed GitHub or GitLab marketplace already exists.
  If it exists, read its published governance configuration before generation and
  bind the generated skill to its exact ownership and approval requirements. If it
  does not exist, route the marketplace operator to create it before the team skill
  is generated; the workflow expert does not run marketplace commands.

Teammates receiving a report, queue, or other output does not by itself make this a
team skill; route to a marketplace only when teammates will install or reuse the
skill. This is destination routing, not a technical interview. Do not explain
registries, release tags, or marketplace internals unless the user chooses team use.

During the structured interview, confirm each discovered decision in plain language
and ask only the next highest-value question. Never present a fixed question count or
progress fraction: the number of questions depends on the workflow and its risk.

## Trigger

User invokes `/agent-skills-platform` followed by their input:

```
/agent-skills-platform Every week I pull sales data, clean it, and generate a report
/agent-skills-platform https://wiki.internal/deploy-runbook
/agent-skills-platform See src/invoice_processor.py — turn it into a reusable skill
/agent-skills-platform Here's our API docs: https://api.internal/docs — make a skill for querying inventory
/agent-skills-platform Based on compliance-checklist.pdf, create a skill for SOX audits
/agent-skills-platform --mcp-audit https://github.com/vendor/mcp-server — we pay for this data, what skills can we build on it?
/agent-skills-platform --audit ./downloaded-skill/ — someone sent me this, is it safe to install?
```

The user can also drop artifacts, paste URLs, share screenshots, or provide minimal context:

```
/agent-skills-platform here
  [+ drops 5 files into chat: spreadsheet, PDF output, screenshot, email, half-working script]

/agent-skills-platform [pastes 2 URLs and a half-sentence]
  https://apps.fas.usda.gov/psdonline/app/index.html
  same thing as the wasde extractor but for this

/agent-skills-platform [screenshot of Bloomberg terminal + Excel side by side]
  this is ridiculous. there has to be a better way

/agent-skills-platform freight

/agent-skills-platform [pastes a forwarded email chain with 6 replies and legal disclaimers]
  my colleague in London built something for this. can we do the same?

/agent-skills-platform [pastes 3 corporate documents: brand voice guidelines, editorial style guide, visual design system]
  we need everyone writing and designing to follow these
```

The user can also activate naturally without the prefix:

```
Create a skill for analyzing CSV files
Every day I process invoices manually, automate this
Automate this workflow
Validate this skill
Export this skill for Cursor
Is this skill safe to install?
Audit this skill before I run it
What does this skill have access to?
```

## How the Factory Works

Raw material goes in. A validated, security-scanned, self-contained skill comes out.

### Evidence-Based Intent Derivation

Before any phase begins, triage whatever the user provided. Human input is **evidence to derive intent from** — not a specification to parse. Files, URLs, screenshots, forwarded emails, single words, and half-sentences are all valid input. The absence of a well-formed description is not the absence of intent.

**Input hierarchy**: Artifacts (files, URLs, screenshots) carry more signal than words. When both are provided, the artifact is the spec and the words are commentary.

**Input triage** — classify what the user provided before proceeding:

- **Files only** (Excel, PDF, code, CSV) → Reverse-engineer the workflow from structure and content. Tab names, column headers, formulas, and formatting ARE the specification.
- **URLs only** → Fetch each URL. Understand the data source. Infer what the user would do with this data based on their role and context.
- **Screenshot/image** → Read visually. Identify: what tool is shown? What data? What manual step is visible? What is the pain?
- **Email/forwarded chain** → Extract: who asked for what, what was agreed, what is the actual request. Ignore disclaimers, scheduling, CC lists.
- **Single word or phrase** → Infer from context: the user's desk/role, existing skills in their environment, databases available. Present the most likely interpretation and confirm.
- **Mixed (files + sentence)** → The files are the spec. The sentence is commentary. Cross-reference both.
- **"here" + files** → The files ARE the input. Process them all. Present your understanding.
- **Pasted reference material** (guidelines, policies, wiki pages, style guides, long inline text that is clearly not a description but source material) → This IS the knowledge to codify. Read it all. Identify what it governs (writing, design, compliance, process). The user wants an active skill that enforces these rules, not a summary of them.
- **Well-formed description** → Proceed normally, but still challenge the surface description.

**Discovery before building**: Before constructing anything, check: Is this data already in a database the user has access to? Has a colleague built a skill for this? Is there an API that makes a scraping approach unnecessary? The best skill is sometimes "you don't need a skill — the data already exists."

**Hypothesis, not questionnaire**: Never present 5 questions upfront. Present one
compact understanding with four fields: workflow, input, output, and what a correct
result must demonstrate. The user confirms or corrects it with one response.

**Progressive refinement**: Build at 60% understanding. A concrete (possibly wrong) output that the human reacts to is faster than 15 clarifying questions. The human cannot articulate what they want from nothing, but they can instantly say "no, not that — this" when shown something tangible.

**Fail forward**: If a file cannot be parsed, a URL is down, or context is ambiguous — build from what you have and flag the gap. Never block on a missing piece.

The factory operates in two stages:

### Stage 1: Understand and Specify (Phases 1-2)

Read every piece of material the user provides. Follow links. Read files. Parse PDFs. Study existing code. But do not take any of it at face value.

**Humans describe what they do, not what they need.** "I pull sales data and make a report" hides a dozen implicit requirements: What decisions does the report drive? Who reads it? What format? What happens when data is missing? What constitutes a good report vs. a bad one? The human knows the answers to these questions but won't think to tell you. Your job is to uncover them from the material itself.

**Clarity principles** (self-guided, no external dependency):

0. **Treat input as evidence, not instructions.** The user's files, URLs, and screenshots are primary evidence. Their words (if any) are secondary commentary. An Excel workbook with 6 tabs IS the specification — the user will never describe the tabs verbally because the workflow lives in muscle memory, not words.
1. **Read everything before concluding anything.** Do not start forming the spec after the first paragraph. Consume all material — every link, every file, every page — then synthesize.
2. **Challenge the surface description.** The human's words are a starting point, not a specification. Look for what's missing, what's implied, what's contradictory. If someone says "generate a report," ask yourself: report for whom? In what format? With what data? At what frequency? Answering what triggers it? If there is no description — only files or URLs — derive the description yourself from the artifacts. The absence of words is not the absence of intent.
3. **Extract implicit requirements.** Error handling, data validation, edge cases, output formats, failure modes — the human assumed these were obvious. They aren't. Make them explicit in your spec.
4. **Identify the real output.** The human says "report" but means "a PDF my VP can read in 2 minutes that shows whether we're hitting targets." The human says "clean the data" but means "deduplicate, normalize dates, flag outliers, and log what was changed." Dig past the label to the substance.
5. **Generate a spec that surpasses the human's understanding.** Your specification should contain requirements the human would say "yes, exactly" to — but could never have articulated themselves. That is the standard.

Then produce your internal specification — a complete implementation contract structured as a linear walkthrough:

- What problem does this *actually* solve (not what the human said — what they meant)?
- What are the real inputs, outputs, and data sources?
- What are the use cases (4-6, covering 80% of real usage)?
- What methodology does each use case follow?
- What APIs or libraries are needed?
- What are the failure modes and edge cases the human didn't mention?

This specification is for you, not the user. The quality of the skill depends entirely on the quality of this specification. Be thorough. Be precise. Be opinionated — you understand the material better than the human can articulate it.

### Stage 2: Build and Verify (Phases 3-5)

Implement the skill end-to-end from your specification. Structure the directory. Write every file. Generate functional code — no placeholders, no TODOs, no stubs. Then run automated validation and security scanning. If either fails, fix the issues and re-run. Do not deliver a skill that fails its own quality gates.

```
Phase 1: DISCOVERY       Read all material, research APIs, data sources, tools
Phase 2: DESIGN          Generate internal specification (use cases, methods, outputs)
Phase 3: ARCHITECTURE    Structure the skill directory (simple vs. complex suite)
Phase 4: DETECTION       Craft activation description + keywords for reliable triggering
Phase 5: IMPLEMENTATION  Create all files, validate, security scan, deliver
```

The user's raw material supplies the domain evidence. The factory supplies the
implementation. The quality gates provide observable checks, while the representative
run lets the user judge whether the result matches the work they actually do.

**Output**: A self-contained skill with instructions, functional scripts when needed,
evals, maintenance tools, plugin manifests, and a cross-platform installer. Once
installed, users invoke it as `/skill-name`. See `references/architecture-guide.md`
for the package layouts.

## Core Workflow

### Structured interview gate (required before Phase 2)

Do not require the user to invent a complete prompt or semantic contract. Start a
resumable `interview.json` from the problem they can describe. Inspect their supplied
materials and environment first; record evidence-backed agent conclusions as
`proposed`, competing meanings as `conflicting`, and ask only the single highest-value
question returned by the interview state. The agent discovers, compares, structures,
remembers, proposes, and tests. Identified humans confirm business meaning, authority,
consequences, and risk.

Run `python3 scripts/structured_interview.py gate interview.json` before Phase 2.
`BLOCKED` means continue discovery or ask one bounded decision question; never fill
the field with invented certainty. `READY` permits design and generation. Read
`references/structured-interview.md` for commands, states, and authority rules.

### Phase 0: Spec Ideation (only when input is too vague to spec)

Most input names a workflow — skip straight to Phase 1. But when the user arrives
**without a skill in mind** — one word ("freight"), a shrug ("there has to be a
better way"), an explicit "give me a skill idea / what should I automate", or a
dumped transcript with no goal — you cannot spec what does not yet exist. Do not
guess a skill and build it. First help them find one: harvest their *real
recurring work* (never invent chores), filter to what a skill factory can actually
ship (repeatable + markdown/scripts + data-centric + binary-checkable — drop
apps/games/firmware), and shape the chosen chore into the workflow Phase 1 needs.
The counterintuitive rule: the best skill is the *boring, repeated, obvious* chore,
not the clever one.

See `references/spec-ideation.md` for the harvest → filter → shape procedure and
its held-out bellwether.

### MCP Capability Audit (`--mcp-audit` — feasibility map instead of a build)

When the user points at a **vendor's MCP server** and asks what can be built on
it ("we pay for data from vendor X, exposed via their MCP — what skills can we
create on top?"), the deliverable is a *feasibility map*, not code. Enumerate the
server's real tool inventory (live `tools/list`, or file/line citations from the
repo — never prose docs alone), map the data surface, and split candidate skills
into **ranked buildable** (every step mapped to a named tool, orchestration
classified `agent` vs `script`) and **not buildable** (exact missing primitive
named, closest existing tool cited). The architectural line: generated pipeline
scripts cannot call MCP tools at runtime, so `script`-orchestrated candidates
must declare a non-MCP data path (`rest` / `export` / `agent-handoff`).

Outputs: `MCP_AUDIT.md` (human) + `mcp_audit.json` (machine), gated by
`python3 scripts/mcp_audit_validate.py mcp_audit.json` — fix findings until
exit 0. A chosen buildable candidate then enters Phase 1 as a normal build.

See `references/mcp-audit.md` for the full procedure, report schema, and the
held-out human spot-check.

### Skill Audit (`--audit` — vet a skill you did not write)

When the user points at a skill **they did not create** — a download, a colleague's folder, a registry entry — the deliverable is a verdict on whether it is safe to install, not a build.

A skill is not a document. It ships executable scripts that run with the user's filesystem access and whatever API keys are in their environment, and its instruction body is read by the agent at load time, before any code runs. Installing one is taking a dependency on a stranger's software.

Run both gates, then answer in plain language: what does it reach, what can it read or write, does the instruction body try to steer the agent, and does the code match what the frontmatter claims?

```bash
python3 scripts/validate.py <path>
python3 scripts/security_scan.py <path>
```

Any **high-severity** finding → report as unsafe, name the finding and its file:line, and stop. Never install it and never offer a workaround. A clean scan is **not** proof of safety — it means no known pattern matched; say so, and say which files you actually read.

Read `references/skill-audit.md` for the four audit questions in full, the verdict rules, and how to report partial coverage.

### Phase 1: Discovery

Research available APIs and data sources for the user's domain. Compare options by
cost, rate limits, data quality, and documentation. Propose the best technical option
with evidence. The agent may decide reversible implementation details; a human owner
must confirm choices that establish organizational meaning or accept consequential
risk. Update `interview.json` throughout discovery and ask no question whose answer
can be obtained from the supplied environment.

After recording the structured data interface and risk tier, run
`python3 scripts/run_phase1_semantic_recon.py <skill-dir>`. This deterministically
emits `semantic_recon.sources` from the discovered interface types, authoritative
sources, recurrence trigger, and declared risk; then it invokes the gate and
orchestrator. Do not hand-write this list. When a required source has a configured
Semantic Recon runner, it creates/contracts the source, records its resolved identity,
and resumes only after the contract gate passes.

#### Semantic Recon path (default for declared sources)

Before designing a skill that uses any declared live or structured source, run
Semantic Recon by default. This applies to:

1. A source is a `DATA_API`, `DATABASE`, `MCP_SERVER`, `CODEBASE`, or remotely
   served `DATA_FILE`.
2. The source is required by the workflow, regardless of whether reuse or blast
   radius has already been proven.

`--semantic-recon` is retained as a compatibility flag; it no longer opts into the
gate because the gate is automatic. Only a workflow with no external or structured
source may omit Semantic Recon.
Never silently skip the path because probing is inconvenient: if the target qualifies
but access, the blast-radius decision, or the out-of-scope boundary is unavailable,
record `verification-blocked` and do not generate a direct source client.

When this path applies, invoke `/semantic-recon` before Phase 2. Its target profile
must name the blast radius and out-of-scope boundary; freeze holdout questions before
discovery; then use the completed contract rather than re-deriving source behavior.
The generated skill must load exactly one registered `data_contract_<id>`, run its
health check, route requests through `validate_query()`, preserve its provenance
formatter, and treat a refusal or drift report as a safe stop. Add both success and
refusal cases to the generated evals. Record the contract id, resolved path, target
type, required operations, and freshness check in `discovery.json` as a
`semantic_recon` dependency block. Semantic Recon establishes what the source does;
the authorized domain owner still establishes organizational meaning.

See `references/pipeline-phases.md` for detailed Phase 1 instructions.

### Phase 2: Design

Define 4-6 priority analyses covering 80% of use cases. For each: name, objective, inputs, outputs, methodology. Always include a comprehensive report function.

See `references/pipeline-phases.md` for detailed Phase 2 instructions.

**Phase 2 includes an Artifact Opportunity Assessment step.** After the
domain is identified, the creator runs `scripts/artifact_detector.py` on
the description. If the output is visualizable (time series, comparison,
KPIs, or structured rows), one of four bundled React templates is inlined
into the generated SKILL.md along with Claude's artifact emission
protocol. The artifact renders in Claude environments; in other hosts the
component source appears as fenced code and the markdown analysis is
unchanged. See `references/phase2-artifact-assessment.md` for details.

**Override flags** — parse the user's prompt for these tokens BEFORE calling the detector:
- `--no-artifact` anywhere in the user's prompt: skip the assessment entirely and generate the skill without any artifact template, exactly as v4 did. Strip the token from the prompt before passing it to Phase 1.
- `--artifact <name>` (where `<name>` is `line-chart`, `bar-chart`, `kpi-cards`, or `data-table`): skip the detector and inline the named template directly. If `<name>` is not one of the four valid names, reject with an error listing the four valid values and stop. Strip the flag and value from the prompt before passing it to Phase 1.
- `--no-eval` anywhere in the user's prompt: skip the Eval Criteria Definition step (below); the generated skill carries no `evals/` directory and no `run_evals.py`. Strip the token from the prompt before passing it to Phase 1.

When neither flag is present, call the detector and let it decide.

**Phase 2 also includes an Eval Criteria Definition step.** After the use
cases are defined, derive the skill's loss function: 3–6 binary checks (each
graded by a shell `command` or flagged `llm-judge`) plus at least 3 golden
cases — seeded from the user's artifacts when available, otherwise synthesized
as input-only `pending-first-green` cases. Present them for a one-word
thumbs-up. The spec is written in Phase 5 to `evals/<name>.eval.md` and ships
with the skill as an instant regression test, formatted so
`autoresearch-universal` consumes it directly (its rule 18). Eval generation is
**on by default**; `--no-eval` opts out. See
`references/phase2-eval-assessment.md` for criteria rules, the golden-case
strategy, the JSON spec format, and the optimize handoff.

**Phase 2 also classifies software mutation.** If the generated skill creates or
modifies application code, schemas, models, persistence, serialization, caches,
synchronization, migrations, or stateful features, review the affected representation
before designing the implementation. Name the affected structures, invariants, single
sources of truth, invalid states that must be unrepresentable, and allowed state
transitions. Unknown invariants block implementation; do not substitute a generic
checklist. Non-software skills declare that this conditional review does not apply.
Read `references/discovery-metadata.md` for the schema, then record the result in
`discovery.json`.

**Phase 2 also classifies structured data interfaces.** If the generated skill reads
an API, MCP tool/resource, database, structured file, event stream, or schema
registry, establish the data contract before designing its processing logic. Inspect
authoritative documentation and, when safely accessible, one representative sample;
record entities, identifiers, relationships, field semantics, invariants, freshness
and pagination, nullability, and blocking readiness checks. Do not infer undocumented
semantics from field names or treat a successful connection as schema proof. Missing
authority or unresolved ambiguity blocks useful execution. Non-structured workflows
declare that this conditional contract does not apply. Read
`references/discovery-metadata.md` for the schema.

For a source that qualified for the Phase 1 Semantic Recon path, the completed
Semantic Recon contract is the data contract. Do not replace it with a one-sample
inventory or duplicate its rules in prose; reference its identity and enforce its
validator at runtime.

**Phase 2 also classifies organizational semantics.** When a correct answer depends
on business definitions, scope, grain, units, time interpretation, or which source
wins, require the human domain owner to approve a versioned semantic contract. Record
ordered source precedence, owner, validity and review dates, exact dependencies, and
the legitimate `answer`, `ask`, and `refuse_unknown` outcomes. The agent may draft and
document this representation but cannot establish authority. Unresolved meaning must
ask the declared clarification or refuse. Skills with no organizational interpretation
declare that this conditional contract does not apply. Read
`references/discovery-metadata.md` for the schema.

### Phase 3: Architecture

Structure the skill using the Agent Skills Open Standard:

- **Simple Skill**: Single SKILL.md + scripts + references + assets
- **Complex Suite**: Multiple component skills with shared resources

**Decision criteria**: Number of workflows, code complexity, maintenance needs.

See `references/architecture-guide.md` for decision logic and directory structures.

### Phase 4: Detection

Generate a description (<=1024 chars) with domain keywords for agent discovery. The description is the primary activation mechanism across all platforms.

See `references/pipeline-phases.md` for detailed Phase 4 instructions.

### Phase 5: Implementation

Create all files in this order:

1. Create directory structure
2. Write **SKILL.md** — starts with `# /skill-name`, includes trigger section with invocation examples, spec-compliant frontmatter
3. Write **AGENTS.md** — companion instruction file for maximum cross-tool reach (~15 tools read AGENTS.md). Contains skill purpose, activation triggers, usage instructions, and a reference to SKILL.md for full details. Follows the AAIF-governed AGENTS.md format
4. Implement Python scripts (functional, no placeholders, no TODOs). **For a multi-script pipeline**, also emit a single `scripts/run_pipeline.py` orchestrator that runs the steps in order and wires output→input **in code** — so the agent runs one command instead of sequencing steps from prose. Skip for genuinely interactive/branching skills. **If any pipeline step invokes an LLM**, follow the LLM-step contract in `references/phase5-orchestration.md`: model id resolved from `--model` argv / `$EVAL_MODEL` env with a pinned default, and runtime-reported usage written to the `{output}.usage.json` sidecar — so `run_evals.py --rollout --model A --model B` can price the task per model. See `references/phase5-orchestration.md`
5. Write references (detailed documentation the skill loads on demand)
6. Write assets (templates, configs)
7. **Emit the eval spec** (skip if `--no-eval`): write `evals/<name>.eval.md` (the binary checks + golden cases derived in Phase 2, one marked `"split": "test"` as the holdout, plus a `judge` block with a pinned model and known-bad canary when any criterion is `llm-judge`) and copy `scripts/run_evals_template.py` → the generated skill's `scripts/run_evals.py`. See `references/phase2-eval-assessment.md`
   Also write `evals/caliper/<name>.eval.yaml` from `references/templates/caliper-eval-template.yaml` (happy path, edge case, silence probe; asserts mirror the criteria above) so the marketplace operator's agent can measure the skill inside a real agent with `team_marketplace.py reliability`. See `docs/CALIPER.md`
7.5. Write **`discovery.json`** with the required decision contract (`question`,
   `trigger`, `decision`, `evidence`, and `success_measure`), plus the real-world
   outcome, intended users, input types, output artifacts, use cases, invocation
   examples, permissions/systems, typical completion time, declared platform
   compatibility, environment discovery/readiness, risk and mutation boundaries,
   the conditional software-mutation representation review, the conditional structured
   data-interface contract, the conditional governed semantic contract,
   and the conditional Semantic Recon dependency block when that path ran,
   positive/negative routing tests, and support tier. Read
   `references/discovery-metadata.md`. Never
   generate a skill without the five decision-contract fields; do not invent
   compatibility certification during creation.
   If the user has named a target governed marketplace and its published governance
   configuration identifies the responsible owners and required intake state, also
   write those exact values as `metadata.owners` and `metadata.approval_status` in
   `SKILL.md`. Do not guess an owner, approver, department, or approval status when
   no target marketplace is known; leave organizational assignment to intake.
7.6. Copy the ready **`interview.json`** into the generated skill root. Run
   `python3 scripts/structured_interview.py gate <skill>/interview.json` immediately
   before copying it. A blocked state stops generation; never downgrade a confirmed
   field to a proposal or remove conflicts to pass the gate.
8. Generate both installers deterministically with **`python3 scripts/render_installers.py <skill-directory>`**. Never copy the factory's root `install.sh` or `install.ps1`; the renderer binds the generated skill name and version into the canonical templates and marks `install.sh` executable.
8.5. Generate `.claude-plugin/plugin.json` + `marketplace.json` from `scripts/claude-plugin-template/` (placeholders from frontmatter — makes the skill installable via `/plugin marketplace add`), and **ship the evolution toolkit and local success ledger**: copy `scripts/evolve_template.py` → `scripts/evolve.py`, `scripts/success_ledger.py`, plus the staleness/drift/dep-health modules. Also copy `scripts/wiki_maintenance_template.py` → `scripts/wiki_maintenance.py`, then run `python3 <skill>/scripts/wiki_maintenance.py init`. This creates an optional, non-runtime `raw/` + `wiki/` learning layer: evidence is captured before a maintainer drafts a pattern; only an atomic candidate that passes existing evaluation, security, and pipeline gates may change an active skill. The runtime agent must receive approved skill files only—never `wiki/`. See `references/pipeline-phases.md` Steps 6.5–6.6
9. Write `README.md` (multi-platform install instructions showing the `/plugin marketplace add` path for Claude Code and `git clone` to each tool's **native** path)
9.5. Build the normalized IR with **`python3 scripts/skill_graph.py build <skill> --output <skill>/skill.graph.json`**. This typed artifact/dependency graph is the validation source of truth; the five phases remain its user-facing projection. Read `references/skill-graph.md` for its schema and invariants.
10. Run **`python3 scripts/skill_graph.py run <skill> --jobs 4`**. It blocks unreachable expected outputs and missing deterministic orchestrators, then runs spec, security, pipeline, and eval-schema gates concurrently with content-addressed caching. All constraints and gates must pass. Record `gates_passed` with the creation run ID.
11. **Auto-install on the current platform** (see below)
12. **Run one safe representative use case** using a supplied artifact when possible,
    otherwise a local fixture. Never send messages, write production data, purchase,
    publish, or trigger another consequential action merely to verify a skill; use a
    dry run or sandbox. If safe execution needs missing credentials, data, or authority,
    stop with `verification-blocked` and one exact setup action. Set
    `ASC_RUN_EVENT=representative_run_passed` and `ASC_RUN_ID=<creation-run-id>` so
    the instrumented pipeline records the first result without double-counting it as
    an ordinary run.
12.5. **Generate `VERIFICATION.md`** from the completed quality evidence. Run
    `python3 scripts/generate_verification.py <skill> --run-kind representative --environment <current-platform>`;
    use `--run-kind live` only after a real external workflow succeeds. The report
    is an evidence artifact, not marketing prose: it records gate states, eval counts,
    installed environments, the 17-environment compatibility declaration, and a bound
    skill version, Git commit, and content fingerprint. Publication must reject a
    missing, failed, or stale report.
13. Report the result using the handoff contract below, including one invocation and
    one correction command. Put eval/optimization details behind an advanced label.

### Auto-Install After Creation

After the skill passes validation and security scan, install it immediately on the user's current platform. Do not ask the user to run `install.sh` manually — you are already running inside their environment and can detect their platform.

**This path is for skills the factory just built.** A skill that came from anywhere else — a download, a colleague, a registry, a repo — must clear `--audit` first (see above). Auto-install never runs on an unscanned imported skill: the scan is what makes the install safe, and a skill this factory did not produce has not been scanned yet.

Detect the platform by which config directory exists (`~/.claude/`, `~/.copilot/`, `.cursor/`, `~/.gemini/`, and ten more), install to that tool's **native** path, then symlink into `~/.agents/skills/` so tools reading the universal path find it too. Some platforms need the SKILL.md adapted to their own format.

Read `references/distribution-guide.md` for the full detection table, the per-platform paths, the confirmation message to show the user, and the `install.sh` fallback when detection fails.

### Share With Your Team (Post-Creation)

After the representative run succeeds and the user can see the result, ask whether
they want to share the skill with their team. Sharing is a separate next step, not
part of first-skill completion.

Corporate users don't know what a registry is, how to `git push`, or what `skill_registry.py` does. They just want their colleague to have the same skill. If they say yes, you do all of it: `git init`, create the remote with whichever CLI is authenticated (`gh` or `glab`), tag it `agent-skill` for org-wide discoverability, and hand back a one-line `git clone` command they can paste into Slack.

If they say no, that is fine — the skill is installed and working, and they can share later.

After a successful share, record `skill_shared`; do not record an offer, declined
share, failed publication, recipient identity, repository name, or organization.

Read `references/distribution-guide.md` for the git/`gh`/`glab` procedure, the platform-detection fallback, the shareable one-liner template, team-registry setup, and the update-check flow.

For governed GitHub or GitLab organizations whose primary client is VS Code Copilot Agent
Mode, run `python3 scripts/team_marketplace.py` instead of using the legacy flat registry. It
creates department namespaces, bundle manifests, CODEOWNERS, provider-native review/release workflows,
schema-v2 quality evidence, and exact version-pinned installs. Runtime
shell access must never be pre-approved in a marketplace skill. Read the governed
marketplace section of `references/distribution-guide.md` before initializing or
migrating a team repository.

For an organizational readiness decision, run the blind four-role protocol in
`docs/ORGANIZATIONAL_ACCEPTANCE.md`. Keep administrator, creator, operator, and
consumer contexts and workspaces isolated. Give each role only public documentation
and artifacts legitimately published by the prior role. Any implementation hint or
direct assistance makes that run a failure rather than a successful demonstration.

### Completion Handoff Contract

Use exactly one of these states:

- **verified** — gates passed, installation succeeded, and a representative safe run
  produced an inspectable result.
- **verification-blocked** — build and gates passed, but a representative run needs
  missing credentials, data, or user authority. State the blocker and one exact action.
- **installed** — installation succeeded but the user explicitly declined the run.
- **failed** — a build, gate, installation, or representative run failed. State the
  failing check and the next repair action; never use success wording.

For `verified`, lead with what now works. Then show the result location or short
preview, the exact `/skill-name` invocation, a compact list of gates passed, and:

```bash
python3 <skill>/scripts/evolve.py --correct "what the result got wrong"
```

Do not lead with file counts, architecture, or internal phase names. Put those under
`Advanced details` only when useful. After the handoff, ask the user to judge the
result before offering team sharing.

### Generated SKILL.md Format

Generated names must end with `-skill`, match the directory, and use lowercase
kebab-case. Frontmatter carries `name`, an activation-focused `description`, license,
author, version, creation/review dates, and any external dependency or schema
expectations. The body starts with `# /skill-name`, includes trigger examples and a
`## Gotchas` section, and stays under 500 lines. Read `references/pipeline-phases.md`
Phase 5 for the maintained template.

**Every generated skill carries a `## Gotchas` section.** It holds the environment-specific facts that defy reasonable assumptions: the field that is a string with commas, the endpoint that returns 200 on failure, the step that must run twice. Sources are the Phase 1 quirks list and every correction made while verifying the skill in Phase 5. `None known` is a valid value; inventing gotchas to fill the section is not — a fabricated gotcha teaches the agent a false constraint it will then work around. `validate.py` warns when the section is missing. Full guidance in `references/pipeline-phases.md` (Phase 5, Step 2).

**Critical**: Every skill the factory produces must be invocable with `/skill-name` on any platform. The generated skill is software that gets installed and used — not a document to read.

## Architecture Decision

Use a simple skill for one or two related workflows. Use a suite for three or more
genuinely distinct workflows or separate team ownership. Read
`references/architecture-guide.md` for the full decision framework and layouts.

## Cross-Platform Support

Generated skills work across 17 tools in 3 tiers. Every generated skill outputs both **SKILL.md** (skill definition, ~15 tools) and **AGENTS.md** (instruction file, ~15 tools) to maximize reach.

- **Tier 1 — native SKILL.md** (12 tools: Claude Code, Copilot, Codex, Gemini, Kiro, Goose, OpenCode, Cline, Roo, Kilo, Factory, Antigravity). Installed as-is, no conversion.
- **Tier 2 — auto-adapted** (Cursor `.mdc`, Windsurf and Trae `.md` rules, Junie `guidelines.md`). `install.sh` rewrites SKILL.md into the native format.
- **Tier 3 — manual integration** (Zed, Augment, Aider, Continue.dev). The user copies the body into the tool's own config file.

`scripts/platforms.py` is the canonical registry of all 17 platforms and their paths; the installers are checked against it in CI.

Read `references/cross-platform-guide.md` for the per-platform path tables, install commands, and adaptation rules.

### Companion AGENTS.md

Every generated skill also outputs an `AGENTS.md` alongside SKILL.md, extending reach to tools that prioritize it over SKILL.md (Codex CLI, Augment, Continue.dev, Zed). It carries the skill's purpose, activation triggers, usage, and its `## Gotchas` entries in full — those tools never open SKILL.md.

## Validation and Security

After generating a skill, run:

- **Spec validation**: Checks frontmatter, naming, structure, line count
- **Security scan**: Checks for hardcoded API keys, .env files, dangerous code patterns, instruction-body prompt injection (override/concealment/exfiltration phrases, hidden unicode, encoded blobs), and undeclared network endpoints in scripts

```bash
# Validate a skill
python3 scripts/validate.py path/to/skill/

# Security scan
python3 scripts/security_scan.py path/to/skill/
```

For factory-created skills, prefer the unified graph gate; the individual commands
above remain useful for focused diagnosis:

```bash
python3 scripts/skill_graph.py run path/to/skill/ --jobs 4
```

## Other Front Doors

Each of these is a mode of the same factory, documented in full in its own reference.

| Mode | Trigger | Read |
|---|---|---|
| **Export** | "export this skill for Cursor" | `references/export-guide.md` |
| **Templates** | a domain with a prebuilt blueprint (financial, climate, e-commerce) | `references/templates-guide.md` |
| **Multi-agent suite** | "create a financial analysis suite with 4 agents" | `references/multi-agent-guide.md` |
| **Interactive wizard** | "walk me through creating..." | `references/interactive-mode.md` |

```bash
python3 scripts/export_utils.py path/to/skill/                    # all platforms
python3 scripts/export_utils.py path/to/skill/ --variant desktop  # or: api
```

## Learning & Evolution

Every generated skill ships its own learning loop — the eval harness plus a self-maintenance command:

- `run_evals.py --rollout` runs the skill on its golden inputs and scores real output
- `--promote` captures first-green baselines; later runs are compared against them (regression gate)
- `--judge` grades `llm-judge` criteria with a judge pinned in the spec (model + temperature); a known-bad canary must fail every criterion or the judge run is invalid
- A `"split": "test"` holdout case is scored only at release, never fed to an optimization loop
- `evolve.py` runs staleness/dependency/drift checks + the rollout in one command; every failure appends its raw evidence to the skill's `EVOLUTION.md`, which feeds a regenerate pass
- `evolve.py --correct "<what it got wrong>"` turns a correction into a proposed `SKILL.md` edit, an executable knowledge-retention regression under `evals/corrections/`, and a versioned patch recommendation in `EVOLUTION.md`
- `success_ledger.py` records only pseudonymous lifecycle metadata and reports verified creation, reuse, durable activity, correction recovery, and sharing locally. Run `python3 scripts/success_ledger.py summary`; read `references/product-success.md` for the privacy boundary and formulas

**Tell the user about `--correct` when you hand over a skill.** The deepest expertise in any workflow is never stated up front — people cannot describe a process they run from muscle memory, which is why this factory reads artifacts instead of interviewing. But the same person recognizes a wrong output instantly. `--correct` is the capture point for that moment, and it is how a skill's `## Gotchas` accumulates real knowledge over its life instead of being frozen at whatever could be extracted on day one.

Read `references/agentdb-integration.md` as a design sketch only — it describes a future episodic learning layer that is NOT implemented; never present it as current behavior.

## Quality Standards

**Always**:
- Complete, functional code (no TODOs, no `pass`)
- Detailed docstrings and type hints
- Robust error handling
- Real content in references (not "see docs")
- A `## Gotchas` section carrying the environment-specific facts that defy reasonable assumptions
- Explicit "run this" / "read this" labels — every `scripts/` mention leads with a run command, every `references/` mention with a read cue
- Configs with real values

**Never**:
- Placeholder code or empty functions
- `api_key: YOUR_KEY_HERE` without env var instructions
- SKILL.md over 500 lines
- Restating what the model already knows — generic error-handling advice, definitions of standard formats, "validate inputs". Every such line spends context to teach the agent something it already has.
- Platform-specific hacks

See `references/quality-standards.md` for complete standards.

## Naming Convention

Every generated skill name must end with `-skill`. This suffix makes skills instantly discoverable across GitHub and GitLab organizations — teams can search `*-skill` and find every skill in their org.

**Format**: `{domain}-{objective}-skill`

**Rules**:
- Must end with `-skill`
- 1-64 characters total, lowercase letters, numbers, and hyphens
- Must match parent directory name
- Must not contain consecutive hyphens

**Examples**: `sales-report-skill`, `csv-cleaner-skill`, `deploy-checklist-skill`, `stock-analyzer-skill`

**Suites**: `{domain}-suite` (suites are not suffixed with `-skill` — they contain skills)

The `-skill` suffix also serves as a signal to the agent: when it sees a repo or directory ending in `-skill`, it knows this is installable, invocable software — not documentation or a regular project.

## Gotchas

- Generated skills end with `-skill`; this factory retains the historical
  `agent-skills-platform` name for invocation and installation compatibility.
- A representative verification run must use dry-run, sandbox, or local fixtures when
  the real workflow has consequential external effects.

## Reference Files

Read these on demand — each one when its moment arrives, not upfront.

| File | When to read it |
|------|----------|
| `references/spec-ideation.md` | Phase 0 front door: turn vague input / "give me a skill idea" into a grounded, skill-shaped spec |
| `references/mcp-audit.md` | `--mcp-audit` front door: vendor MCP server → capability map, ranked buildable skills, not-buildable list with named gaps |
| `references/skill-audit.md` | `--audit` front door: the four audit questions, verdict rules, and how to report partial coverage on a skill you did not write |
| `references/distribution-guide.md` | After the gates pass: platform detection, team distribution routing, and update checks. For governed marketplace operations, follow the linked `docs/TEAM_MARKETPLACE.md` command timeline. |
| `references/pipeline-phases.md` | Detailed Phase 1-5 instructions |
| `references/architecture-guide.md` | Simple vs Suite decision, refactoring, cross-component communication, versioning |
| `references/templates-guide.md` | Template-based creation |
| `references/interactive-mode.md` | Interactive wizard docs |
| `references/multi-agent-guide.md` | Suite creation, orchestration patterns, routing logic |
| `references/agentdb-integration.md` | Future learning-layer design sketch (not implemented) |
| `references/cross-platform-guide.md` | Platform compatibility matrix |
| `references/export-guide.md` | Cross-platform export system |
| `references/quality-standards.md` | Quality standards, dependency management, testing strategy |
| `references/phase4-detection.md` | Detection & keyword-design craft reference |
| `references/phase2-eval-assessment.md` | Phase 2 eval-criteria step, golden-case strategy, spec format, autoresearch handoff |
| `references/phase5-orchestration.md` | Phase 5 pipeline orchestration: single run_pipeline.py entry-point, deterministic sequencing, check_pipeline.py |
| `references/skill-graph.md` | Normalized artifact graph, blocking reachability constraints, parallel gates, and content-addressed caching |
| `references/product-success.md` | Local lifecycle event schema, privacy boundary, Durable Active Skills definition, and metric formulas |
| `references/discovery-metadata.md` | Generated discovery.json schema used by governed marketplace search and skill pages |
| `references/structured-interview.md` | Resumable evidence/authority interview and pre-generation gate |
| `references/semantic-contract-experiment.md` | Bounded three-skill, four-configuration evidence protocol for semantic-contract product success |
