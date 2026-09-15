# Product scope: the governed skill lifecycle control plane

**Research snapshot:** 2026-08-26  
**Decision horizon:** Revisit this boundary quarterly, or when the Agent Skills
specification makes a breaking change. Do not expand it in response to individual
vendor features.

## Product definition

Agent Skills Platform turns a human workflow into a portable, evidence-backed Agent
Skill and governs that artifact from proposal through retirement across the agent
platforms an organization already uses.

An Agent Skill is a reusable workflow package that guides an agent from a recognized
situation to a verified outcome. It can use retrieved knowledge, MCP tools, APIs,
deterministic scripts, and agent judgment, but it is not itself a RAG system, MCP
server, or agent runtime.

**RAG supplies knowledge. MCP supplies capabilities. The harness supplies execution.
A skill organizes them into a governed path toward a verified outcome.**

It is the **control plane for skill supply**, not an agent runtime, model host, MCP
gateway, identity provider, endpoint manager, or general marketplace for every agent
extension.

The unit it governs is not merely a `SKILL.md` file. It is a versioned workflow
package containing:

- a decision contract: question, trigger, decision, evidence, and success measure;
- routable instructions with progressively disclosed references and assets;
- deterministic scripts and validation checks where repeatability matters;
- an environment contract covering tools, APIs/MCP servers, schemas, permissions,
  compatibility, readiness checks, and mutation boundaries;
- evals, representative-run evidence, provenance, ownership, and lifecycle state.

## Why this boundary is durable

The open format has converged on a small stable core: a directory with `SKILL.md`,
optional scripts, references, and assets, loaded through progressive disclosure.
The specification deliberately leaves execution and distribution to clients
([Agent Skills specification](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)).

Major clients now implement the same artifact differently. GitHub supports project
and personal locations plus `gh skill` discovery, install, update, and publication
([GitHub Docs](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)).
Cursor adds nested scope, manual invocation, modes, and plugin distribution
([Cursor Docs](https://cursor.com/docs/skills)). Anthropic separates Claude Code,
claude.ai, API, and managed-agent surfaces, with different sharing and runtime
constraints ([Claude Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).
Microsoft supports file-, code-, class-, and MCP-backed skill providers
([Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/agents/skills)).

Those differences will keep changing. The portable workflow package and its trust
evidence are the stable layer. The product owns that layer and uses replaceable
adapters for the rest.

## The five product capabilities

Every shipped feature must strengthen at least one capability below.

| Capability | Product responsibility | Proof of success |
|---|---|---|
| **Capture** | Extract a consequential, repeatable workflow from a person, documents, examples, or prior runs. Discover required APIs, MCP tools, schemas, and constraints before prescribing execution. | The creator confirms the decision contract and representative cases. |
| **Compile** | Generate a spec-conformant, portable package with minimal instructions, deterministic helpers, environment discovery, readiness gates, and safe mutation boundaries. | The package validates and runs without factory-source dependencies. |
| **Prove** | Evaluate routing, non-triggering, instruction following, outputs, coexistence, security, compatibility, and representative outcomes; for Claude Code and Codex, measure activation and instruction following inside the real agent runtime (Caliper). Bind evidence and attestations to immutable content. | A reviewer can reproduce the claimed behavior from the committed artifact. |
| **Govern** | Enforce ownership, separation of duties, approval policy, risk tiers, versioning, lineage, update, rollback, quarantine, retirement, clean recreation, staleness, and audit history. | An operator can explain what is active, why it is trusted, who owns it, and how to stop it. |
| **Deliver and learn** | Make approved skills discoverable by outcome; install exact versions through governed adapters; collect consented, privacy-safe activation, correction, success, and retention signals. | Another team discovers and reuses a skill without its author, and evidence informs the next lifecycle decision. |

## Required lifecycle

The artifact lifecycle is fixed:

```text
proposal → discovery → generated → evaluated → approved → published
                                      ↓              ↓
                                   rejected     quarantined → retired → recreated
```

An installed skill also has an environment state:

```text
unconfigured → discovering → ready → executing
                    ↓           ↓         ↓
               incompatible  degraded  blocked
```

Publication means the artifact is approved. It does **not** claim that every
consumer environment is ready. A skill must inspect and prove its local prerequisites
before consequential execution.

## Product boundaries

### In scope

- Workflow capture, generation, validation, repair, and eval authoring.
- Organizational registry, policy-as-code, evidence, provenance, and lifecycle.
- Outcome-based discovery, support/compatibility disclosure, and governed bundles.
- Vendor adapters for publishing, installing, pinning, updating, and removing the
  same approved package.
- Privacy-safe product evidence needed to decide whether to improve or retire a skill.

### Out of scope

- Hosting models, agent sessions, sandboxes, or long-running orchestration.
- Building a competing MCP registry, API gateway, secret manager, IAM system, EDR,
  or enterprise app store.
- Reimplementing vendor-native rules, hooks, commands, agents, plugins, or UI unless
  required by a thin distribution adapter.
- Guaranteeing the truth of third-party documentation or compatibility without a
  fresh environment check.
- Autonomous production mutation without the creator-defined approval boundary.

Integrate with those systems. Do not absorb them.

## Evidence behind the scope

Three market facts determine the product shape.

1. **Authoring quality is the bottleneck.** A 2026 study of 138,133 public skills
   found 91.8% had at least one detected defect; weak routing, bloated bodies, and
   poor resource organization dominated. Spec-aware prompting, linting, repair, and
   safety gates improved quality
   ([Zhang et al.](https://arxiv.org/abs/2608.08453)). Another study found skill
   smells in more than 99% of examined `SKILL.md` files and that smells rarely
   disappeared through normal evolution
   ([Hong et al.](https://arxiv.org/abs/2607.01456)).

2. **A skill is executable supply-chain content.** Anthropic tells enterprises to
   review code execution, exfiltration, triggers, coexistence, outputs, ownership,
   versions, and periodic regressions, and to separate authors from reviewers
   ([enterprise guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/enterprise)).
   A large-scale security study found vulnerabilities in 26.1% of 31,132 analyzed
   skills and found script-bearing skills 2.12 times more likely to contain a
   vulnerability
   ([Liu et al.](https://arxiv.org/abs/2601.10338)). These findings justify gates;
   scanners alone are not proof of safety.

3. **Distribution and runtime remain fragmented.** Anthropic explicitly documents
   that custom skills do not sync across its surfaces, and runtime network/package
   capabilities differ by surface. GitHub and Cursor use different scopes and
   management affordances. Therefore portability certification and adapters belong
   in this product; owning every runtime does not.

Anthropic's current authoring recommendation also starts with evaluations and a
baseline rather than extensive instructions
([authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
That supports the product's evidence-first generation pipeline.

## Feature admission rule

A proposed feature enters the roadmap only when all five answers are **yes**:

1. Does it solve a repeated problem observed in at least two teams or two supported
   platforms?
2. Does it strengthen one of Capture, Compile, Prove, Govern, or Deliver and learn?
3. Can it remain vendor-neutral at the core, with vendor behavior isolated in an
   adapter?
4. Can its success be measured through an automated gate or a blind cross-team task?
5. Is integration insufficient—meaning the product genuinely must own this behavior?

If any answer is no, document the request and reject it from core scope. A platform
adapter may still be justified when customers already use that platform and the
adapter preserves the same lifecycle semantics.

## Product success

The north-star event is:

> A person captures a valuable workflow; an independent operator approves its
> evidence; someone in another team discovers and successfully reuses the exact
> approved version without assistance; the organization can later update, stop,
> explain, or erase and recreate it safely.

Measure the funnel, not inventory size:

1. qualified workflow → first representative pass;
2. representative pass → approved publication;
3. publication → independent activation;
4. activation → successful run without correction;
5. successful run → retained cross-team reuse.

Guardrails are time to quarantine, owner coverage, evidence freshness, regression
rate, permission expansion, and unsupported-environment attempts.

## What not to chase next

Do not build new platform integrations merely because a vendor adds a new skill
folder, invocation control, marketplace UI, or agent wrapper. Update an adapter only
when a target customer needs it and the organizational acceptance test can exercise
it. Do not add speculative metadata; require evidence that it improves routing,
safety, compatibility, or a lifecycle decision.

The control plane now requires environment discovery/readiness, risk-based mutation
boundaries, portfolio-level routing tests, organizational onboarding, and conditional
human-approved semantic contracts. It governs semantic definitions consumed by skills;
it does not become a semantic-layer database, ontology editor, data catalog, warehouse
query engine, or autonomous definition generator. The next maturity step is evidence:
run the bounded three-skill experiment across isolated configurations before expanding
the semantic surface. Runtime probes, identity, analytics, and semantic storage remain
integrations. Everything else is a separate product.

## Stop or move decision gate

Use this gate at the end of every product increment. **Stop building** when any stop
condition is true. Move ahead only when every move condition is true.

### Stop and operate

- The north-star workflow passes and the next proposal does not repair an observed
  failure in Capture, Compile, Prove, Govern, or Deliver and learn.
- The proposal is requested by only one user or vendor and a documented integration
  already handles it.
- Existing skills lack owners, current evidence, cross-team reuse, or operator
  capacity; improve adoption and operations before adding surface area.
- Success cannot be demonstrated by an automated gate or blind cross-team task.
- The change would make this product own a runtime, MCP registry, IAM, secrets,
  endpoints, or a general extension marketplace.

### Move ahead

- Evidence from at least two teams or two supported platforms shows the same blocked
  lifecycle outcome.
- The smallest proposed change strengthens one of the five stable capabilities.
- The vendor-neutral contract remains primary and platform behavior stays in an
  adapter.
- A named owner, measurable success threshold, rollback path, and stopping condition
  exist before implementation.
- Current lifecycle health is acceptable: no unowned critical skill, overdue critical
  evidence, unresolved regression, or failed organizational acceptance gate.

When the stop conditions win, the correct product action is maintenance, onboarding,
measurement, or no work. A quiet roadmap is evidence of discipline, not product
inactivity.
