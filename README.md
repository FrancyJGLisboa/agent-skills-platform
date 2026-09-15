# Agent Skills Platform

**Turn a real workflow into a tested, installable agent skill—then publish it safely to your team.**

![Agent Skills Platform: question to tested skill to governed marketplace](docs/assets/agent-skills-platform-social-preview.png)

[![CI](https://github.com/FrancyJGLisboa/agent-skills-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/FrancyJGLisboa/agent-skills-platform/actions/workflows/ci.yml)
[![Agent Skills Open Standard](https://img.shields.io/badge/Agent%20Skills-Open%20Standard-blue)](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)
[![Platforms](https://img.shields.io/badge/installs%20on-17%20platforms-7c3aed)](docs/INSTALL.md)
[![Version](https://img.shields.io/badge/version-6.1.0-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()

[Website](https://francyjglisboa.github.io/agent-skills-platform/) ·
[Installation](docs/INSTALL.md) ·
[Worker runbook](docs/WORKER_RUNBOOK.md) ·
[Team marketplace](docs/TEAM_MARKETPLACE.md) ·
[Product scope](docs/PRODUCT_SCOPE.md)

Agent Skills Platform turns the way people already work into tested, installable agent
skills. Give it a prompt plus the evidence behind the work—spreadsheets, reports,
emails, screenshots, transcripts, links, or scripts—and it builds a reusable workflow
that a person can inspect, an organization can review, and a team can safely reuse.

```text
/agent-skills-platform

Turn my monthly revenue-variance review into a reusable internal skill.
I attached past reports and the source spreadsheets. The decision is whether to
escalate a material variance. It must not modify source data.
```

The result is not just a prompt: it is an installable skill package with instructions,
functional scripts when needed, evals, security checks, a representative-run record,
and a correction path for real-world learning.

After release, a skill can retain maintenance evidence without turning every log
into runtime prompt context: classified run evidence is captured in `raw/`, recurring
findings become evidence-linked draft patterns in `wiki/`, and only a separately
validated change may update the executable skill. This is a governed maintenance
record, not autonomous self-modification.

## Create your first skill

Choose the path that matches what you need today.

**First question:** is this skill just for you, or will teammates install or reuse the
skill itself?

- **Just for you** — create, verify, and install it privately. No marketplace setup.
- **My team** — create or select a governed GitHub/GitLab marketplace first, so the
  skill inherits real ownership and approval rules.

Teammates receiving a report or queue does not require a marketplace. Use the team
path only when teammates will install or reuse the skill.

### I have a workflow — no code required

Open the AI agent you already use, attach examples of the work, and paste this:

```text
/agent-skills-platform

Turn my monthly revenue-variance review into a reusable internal skill.
I attached past reports and the source spreadsheets. The decision is whether to
escalate a material variance. It must not modify source data.
```

The creator asks for the business decisions only you can authorize, builds and tests
the skill, and shows a representative result. When it is correct, say: **“Publish
this to the Finance marketplace.”**

When the workflow uses an API, database, MCP, codebase, or structured file, Semantic
Recon runs automatically before implementation and creates a pinned data contract.
Use `./install.sh --without-semantic-recon` only for a deliberately local,
source-free installation.

Do not use Git, edit registry files, or run marketplace commands. If the creator is
not installed in your agent, send this section to your marketplace operator.

### My teammates just need to install skills

Give them the [desktop app](docs/DESKTOP_APP.md): download, paste the team-library
link, click Install. Skills land in GitHub Copilot (or the tool they pick) with no
terminal, Python, or Git involved. The same page shows admins how to create a
library in four commands.

### I run the marketplace

Use the [governed team marketplace guide](docs/TEAM_MARKETPLACE.md) to admit,
approve, release, distribute, update, quarantine, and roll back tested skills.

### I am evaluating the platform

Read the [product scope](docs/PRODUCT_SCOPE.md),
[organizational acceptance protocol](docs/ORGANIZATIONAL_ACCEPTANCE.md), and
[technical implementation guide](docs/TECHNICAL_OVERVIEW.md).

## Why teams use it

- **Preserve expert judgment.** A skill captures the question, evidence, decision,
  and success measure behind recurring work.
- **Trust what is shared.** Skills carry validation, security checks, evals, and a
  representative run before they are published; for Claude Code and Codex the
  marketplace can also certify a skill from real agent runs (`reliability`).
- **Learn without runtime bloat.** Maintenance keeps evidence, draft patterns, and
  rejected changes separate from the concise instructions an agent executes.
- **Govern team use.** The marketplace provides ownership, approvals, versioned
  releases, discovery, rollback, quarantine, and compatibility evidence.

## How work moves through the organization

```text
SME supplies examples and approves the result
        ↓
Creator builds and verifies a skill
        ↓
Marketplace operator governs and publishes it
        ↓
Colleagues install an approved version and use it
```

The SME owns business meaning. The marketplace operator owns distribution and policy.
See [roles and handoffs](docs/TEAM_MARKETPLACE.md#roles-and-handoffs).

## See a verified result

The repository includes a live, read-only weather briefing example with a source-linked
result and verification evidence. Start with the
[verification record](docs/verification/2026-08-27-live-weather-briefing.md), then
inspect the [skill package](references/examples/live-weather-briefing-skill).

## Read more when needed

| Need | Read |
|---|---|
| Install on a supported AI tool | [Installation](docs/INSTALL.md) |
| Let non-technical teammates browse and install skills | [Desktop app](docs/DESKTOP_APP.md) |
| Create, correct, and hand off a first skill | [Worker runbook](docs/WORKER_RUNBOOK.md) |
| Run a governed internal marketplace | [Team marketplace](docs/TEAM_MARKETPLACE.md) |
| Test a skill inside a real agent and certify it per runtime | [Caliper pilot](docs/CALIPER.md) |
| Understand scope and product boundaries | [Product scope](docs/PRODUCT_SCOPE.md) |
| Review architecture, validation, and technical controls | [Technical overview](docs/TECHNICAL_OVERVIEW.md) |
| Contribute | [Contributing](CONTRIBUTING.md) |

## What happens behind the scenes

An Agent Skill is a reusable workflow package that guides an agent from a
recognized situation to a verified outcome. It can use retrieved knowledge, MCP
tools, APIs, deterministic scripts, and agent judgment, but it is not itself a
RAG system, MCP server, or agent runtime.

RAG supplies knowledge. MCP supplies capabilities. The harness supplies
execution. A skill organizes them into a governed path toward a verified
outcome.

Reason where interpretation is necessary. Execute and verify with deterministic
controls where reproducibility matters. External models, APIs, and changing data
may vary rather than promising identical outputs.

Humans establish meaning. The factory does not expect you to know the correct
prompt or semantic contract; it asks one bounded question at a time. The flow is:

- Messy problem
- Agent inspects evidence
- Proposed / conflicting meanings
- Human authority decision
- Interview READY
- Build, prove, publish

Every skill is checked as one connected system. The skill graph links its
instructions, scripts, evaluations, and expected outputs. Two structural
requirements confirm that every expected result is tested and every predictable
multi-step workflow has one reliable entry point. Four checks—specification,
pipeline, security, and evaluation schema—run in parallel. Finally, a
representative run proves that the skill produces a useful result. The graph also
enforces `every_expected_is_reachable` and `deterministic_multistep_has_orchestrator`.
After intake, `team_marketplace.py reliability` can run the skill inside each installed
agent runtime k times and certify only what an agent actually discovered and followed
([Caliper](docs/CALIPER.md)).

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
Contributions require the [contributor assignment](CONTRIBUTOR_ASSIGNMENT.md).

## License

MIT. See [LICENSE](LICENSE). Copyright © 2026 Francy J G Lisboa, also known as
Charuto. See [ownership](COPYRIGHT.md).
