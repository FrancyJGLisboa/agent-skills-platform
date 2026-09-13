# Contributing

Thanks for your interest in improving **agent-skills-platform**. This skill
generates cross-platform agent skills, so changes need to keep the generator
correct and its tests green.

## Workflow

1. Read and sign the [Contributor Copyright Assignment](CONTRIBUTOR_ASSIGNMENT.md).
2. Fork the repository and create a feature branch.
3. Make your changes and add or update tests under `scripts/tests/`.
4. Run the checks below — they must pass.
5. Open a pull request describing what changed and why, with the signed assignment.

Pull requests cannot be accepted until the copyright assignment is countersigned.
Discussion, bug reports, and feature requests do not require an assignment.

## Local checks

The tooling is stdlib-only Python; tests run with `pytest`.

```bash
# Run the full test suite (must be green)
uv run pytest scripts/tests/

# Validate a skill's SKILL.md against the spec
python3 scripts/validate.py <skill-dir>

# Verify a skill's script pipeline (compiles, deps declared)
python3 scripts/check_pipeline.py <skill-dir>

# Security scan
python3 scripts/security_scan.py <skill-dir>

# Run every gate a skill package must pass (spec, security, pipeline,
# eval schema, Semantic Recon contracts)
python3 scripts/skill_graph.py run <skill-dir>

# Check that changed skills carry current verification evidence,
# exactly as CI does
python3 scripts/check_verification.py --base origin/main
```

## Changing a bundled skill

Anything under `references/examples/` is a real skill package, so CI holds it
to the same gates a user's skill must pass. Two of those catch contributors
out.

**Semantic Recon contracts.** A skill whose `discovery.json` sets
`data_interfaces.applies` must also declare `semantic_recon.sources` and ship
the contract it names (`.contract_id` plus `code/contract_health.py`).
`skill_graph.py run` fails otherwise, and its error carries the repair.

**Verification evidence binds to a commit.** `VERIFICATION.md` records the
commit that existed when it was generated, and the gate accepts a follow-up
commit whose diff within the skill is *exactly* `{VERIFICATION.md}`. So a
combined commit is rejected even when the evidence itself is current, and
landing a change takes three steps in this order:

1. Commit the behavior change. Include the `## Verification` link that
   `generate_verification.py` appends to `README.md` — it must land here, not
   in step 3.
2. `python3 scripts/generate_verification.py <skill-dir>`
3. Commit `VERIFICATION.md` on its own.

`check_verification.py` prints this sequence whenever it fails, so you do not
need to memorize it.

## Conventions

- **Commits:** conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`,
  `test:`, `chore:`).
- **Style:** PEP 8, type annotations on function signatures, `ruff` clean.
- **Cross-platform parity:** the install scripts ship as bash/PowerShell pairs.
  When you touch one (`install-skill.sh`, `bootstrap.sh`, `install-template.sh`,
  `install.sh`), update its `.ps1`/`.bat` counterpart so
  `scripts/tests/test_install_parity.py` stays green.
- **Single source of truth:** SKILL.md parsing lives in `scripts/skill_document.py`
  and the install-target list in `scripts/platforms.py` — extend those rather than
  re-implementing parsing or hardcoding platform paths.
- **Marketplace contract:** changes to `scripts/team_marketplace.py` must keep its
  tests, README quick start, `docs/TEAM_MARKETPLACE.md`, `docs/INSTALL.md`,
  GitHub Pages, `SKILL.md`, and
  `references/distribution-guide.md` aligned. Examples and fixtures use ACME only.
  Provider-related changes must also update `docs/GITLAB_TEAM_REGISTRY.md` and
  preserve behavioral parity for governance gates and immutable pins.

## Changing the governed marketplace

Run the focused suite first:

```bash
uv run pytest scripts/tests/test_team_marketplace.py -q
python3 scripts/team_marketplace.py --help
```

Keep schema-v1 migration explicit and non-approving. Remote installs require a
semantic-version pin and exact repository skill paths. `--force` may overwrite an
installation; it must never bypass validation, security, pipeline, eval, ownership,
or approval gates.

## Adding a new platform

The most common contribution. A platform addition touches a fixed set of
files — change them together or CI's parity tests will catch the drift:

1. **`scripts/platforms.py`** — add the platform tuple (name, user-level
   install path, project-level install path, detection directory). This is
   the single source of truth the registry and installers read.
2. **Four shell pairs.** Every one enumerates platforms independently, and
   each `.sh`/`.ps1` pair is parity-gated by `test_install_parity.py`:
   - `install.sh` / `install.ps1` — the repo's own self-installer
   - `scripts/install-template.sh` / `.ps1` — bundled into generated skills
   - `scripts/install-skill.sh` / `.ps1` — the universal skill installer
   - `scripts/bootstrap.sh` / `.ps1` — the `curl | sh` one-liner
3. **Docs** — add the platform to the tier table in
   `references/cross-platform-guide.md` (and `docs/INSTALL.md` if it needs a
   per-tool install path). If the platform needs a format adapter (not native
   SKILL.md), document the transformation in the Tier 2 section.
4. **Platform count** — the total is stated in **six** files:
   `README.md`, `SKILL.md`, `references/cross-platform-guide.md`,
   `docs/INSTALL.md`, `references/pipeline-phases.md`, and `docs/index.html`.
   Bump every one in the same PR, and remind a maintainer to update the GitHub
   repo description. Find them all with:

   ```bash
   grep -rn "17 platform\|17 tool" --include="*.md" --include="*.html" .
   ```

Then verify:

```bash
uv run pytest scripts/tests/test_platforms.py scripts/tests/test_install_parity.py
```

`test_platforms.py` cross-checks `platforms.py` against the shell installers,
so a partial addition fails loudly.

**Nothing checks the docs.** Steps 3 and 4 are unenforced — a stale tier table
or a count that still says the old number passes CI. Grep before you push.

## A note on eval specs

Generated skills bundle `run_evals.py` (from `scripts/run_evals_template.py`),
which executes spec-defined command checks via the shell, compares rollout
output against promoted baselines (regression gate), holds out `"split": "test"`
cases from optimization, and — with `--judge` — grades `llm-judge` criteria via
a judge pinned in the spec (with a known-bad canary that must fail). Skills also
bundle `evolve.py` (from `scripts/evolve_template.py`) and plugin manifests
(from `scripts/claude-plugin-template/`). Eval specs are trusted input — only
run evals from specs you or your team wrote.

## License

Accepted contributions are owned by Francy J G Lisboa under the signed
[Contributor Copyright Assignment](CONTRIBUTOR_ASSIGNMENT.md) and distributed under
the [MIT License](LICENSE). Opening a pull request by itself does not transfer
copyright.
