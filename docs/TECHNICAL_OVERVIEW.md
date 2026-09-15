---
permalink: /TECHNICAL_OVERVIEW.html
---

# Technical Overview

This guide is for platform engineers and evaluators. It complements the short
[README](../README.md), which is intentionally written for people deciding whether to
create or operate a skill.

## Product model

An agent skill is a reusable workflow package that guides an agent from a recognized
situation to a verified outcome. It can use retrieved knowledge, MCP tools, APIs,
deterministic scripts, and agent judgment. It is not itself a RAG system, MCP server,
or agent runtime.

The factory turns workflow evidence into a skill with a decision contract: the
question, trigger, supported decision, required evidence, and success measure. It
validates structure, scans for security patterns, runs evals, and performs a safe
representative run before handoff.

## Persistent maintenance knowledge

Each newly generated skill also carries a maintenance-only learning layer:

```text
raw evidence → draft wiki pattern → atomic candidate change → existing gates → accepted or rejected decision
```

`raw/` holds classified, read-only copies of observed evidence. `wiki/` links that
evidence to draft patterns and a candidate-impact ledger. `scripts/wiki_maintenance.py`
creates and validates these records but cannot edit `SKILL.md`; a separate maintainer
or proposer must prepare an atomic patch. The runtime agent receives approved skills
only, never wiki content. This preserves auditability and avoids prompt bloat while
leaving semantic pattern analysis and skill changes subject to evaluation and review.

## Governance model

The marketplace lifecycle is:

```text
create → attest → admit → approve → publish → discover → install
       → use → update → rollback → quarantine → retire
```

The marketplace is the governance layer for ownership, lifecycle state, immutable
versions, compatibility evidence, rollout, quarantine, and rollback. The skill
factory creates the artifact; the marketplace operator governs distribution. Full
procedures: [Governed Team Marketplace](TEAM_MARKETPLACE.md).

Compatibility evidence for Claude Code and Codex can come from real agent runs: the
factory emits `evals/caliper/<skill>.eval.yaml`, and `team_marketplace.py reliability`
runs it inside each installed runtime, binds the run to the released `SKILL.md` hash,
and certifies only what cleared the reliability thresholds
([agent-run reliability](CALIPER.md)).

## Technical references

- [Skill creation and validation instructions](../SKILL.md)
- [Marketplace implementation and operations](TEAM_MARKETPLACE.md)
- [Agent-run reliability evidence (Caliper)](CALIPER.md)
- [Platform installation adapters](INSTALL.md)
- [Structured interview protocol](../references/structured-interview.md)
- [Capability resolver contract](../references/capability-resolver-contract.md)
- [Product boundaries](PRODUCT_SCOPE.md)
- [Organizational acceptance protocol](ORGANIZATIONAL_ACCEPTANCE.md)
