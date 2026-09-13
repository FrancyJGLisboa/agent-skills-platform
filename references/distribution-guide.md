# Distribution: install, share, register, update

Everything that happens **after** a skill passes its gates. Read this when you
have just built a skill and are installing it, when the user wants to share one
with their team, or when setting up a team registry.

The factory's SKILL.md carries the decisions; this file carries the paths,
procedures, and message templates they need.

---

## Governed GitHub Copilot Marketplace

The canonical platform ID is `github-copilot`. Installers continue accepting
`copilot` as a deprecated input alias; registry and certification artifacts emit
only the canonical ID.

The public operator guide is
[`docs/TEAM_MARKETPLACE.md`](../docs/TEAM_MARKETPLACE.md). It places every command
in chronological order. Keep this internal routing reference consistent with it.

Use this path for a centrally governed organization whose analysts work primarily
in VS Code Copilot Agent Mode. GitHub is the control plane; `gh skill` is the
preview/install/release mechanism. The copy-based installer later in this guide is
the fallback while `gh skill` remains in public preview.

1. Initialize a new ACME-only repository scaffold:

   ```bash
   python3 scripts/team_marketplace.py init --name "ACME Skills" --repository ACME/acme-skills --marketplace ./acme-skills
   ```

   To migrate an existing schema-v1 registry, add
   `--from-registry ./legacy-registry`. Migrated entries remain `draft` until
   department, platform, and security owners review them.

2. Add a reviewed skill to a department and bundle:

   ```bash
   python3 scripts/team_marketplace.py add ./report-skill --department finance --bundle analyst-starter --marketplace ./acme-skills
   ```

   Add runs validation, security, pipeline, and eval gates before copying.
   The source `SKILL.md` must declare `metadata.owners`,
   `metadata.approval_status: approved`, author, and version. `allowed-tools` may
   not pre-approve `shell` or `bash`; Copilot asks for runtime permission.

3. Require the generated `governed-marketplace` check and CODEOWNER approval on
   the protected default branch. Apply a restricted `v*.*.*` tag ruleset using
   the exact settings in `GOVERNANCE.md`.

4. Check and publish an immutable release:

   ```bash
   python3 scripts/team_marketplace.py check --marketplace ./acme-skills
   python3 scripts/team_marketplace.py release --tag v1.2.0 --marketplace ./acme-skills
   ```

5. Install a bundle at an exact release for Copilot:

   ```bash
   python3 scripts/team_marketplace.py install --bundle analyst-starter --scope user --pin v1.2.0 --marketplace ./acme-skills
   python3 scripts/team_marketplace.py install --bundle analyst-starter --scope project --pin v1.2.0 --marketplace ./acme-skills
   ```

   Updating means explicitly installing a newer pin. Rollback uses the same
   command with the previous tag and `--force`. Corrections go through the
   skill's `scripts/evolve.py`, its gates, and a pull request—never by editing an
   installed copy.

## Auto-Install After Creation

After the skill passes validation and security scan, install it immediately on the user's current platform. Do not ask the user to run `install.sh` manually — you are already running inside their environment and can detect their platform.

**This path is for skills the factory just built.** A skill that came from anywhere else — a download, a colleague, a registry, a repo — must clear `--audit` first (see above). Auto-install never runs on an unscanned imported skill: the scan is what makes the install safe, and a skill this factory did not produce has not been scanned yet.

**Detection logic** (check in order, install to each tool's **native** path):

```
~/.claude/              exists → Claude Code         → ~/.claude/skills/
~/.copilot/             exists → GitHub Copilot CLI  → ~/.copilot/skills/
.github/                exists → VS Code Copilot     → .github/skills/ (project)
.cursor/                exists → Cursor              → .cursor/skills/ (project only, no global path)
~/.codeium/windsurf/    exists → Windsurf            → ~/.codeium/windsurf/skills/ (global) + format adapt
.windsurf/              exists → Windsurf            → .windsurf/rules/ (project) + format adapt
.clinerules/ or ~/.cline/ exists → Cline             → .clinerules/skills/ or ~/.cline/skills/
~/.gemini/              exists → Gemini CLI          → ~/.gemini/skills/
.kiro/                  exists → Kiro                → .kiro/skills/ (project)
.trae/                  exists → Trae                → .trae/rules/ + format adapt (plain .md)
.roo/                   exists → Roo Code            → .roo/skills/
~/.config/goose/        exists → Goose               → ~/.config/goose/skills/
~/.config/opencode/     exists → OpenCode            → ~/.config/opencode/skills/
~/.agents/              exists → Universal           → ~/.agents/skills/
```

After installing to the native path, **also create a symlink at `~/.agents/skills/`** so the skill is discoverable by tools reading the universal path (Codex CLI, Gemini CLI, OpenCode, Goose, Cline, Roo Code).

**Format adaptation**: For Tier 2 platforms (Cursor, Windsurf, Trae), also generate the native format alongside SKILL.md:
- **Cursor**: Generate `.mdc` file with `alwaysApply: true` and description from frontmatter
- **Windsurf**: Generate plain `.md` rule, respect 6,000 char per-file limit
- **Trae**: Generate plain `.md` rule with `type: Always` frontmatter

**Install action**: Copy or symlink the generated skill directory into the platform's native skill path:

```bash
# Claude Code (user-level):
cp -R ./sales-report-skill ~/.claude/skills/sales-report-skill

# GitHub Copilot (user-level — Copilot's own path, not Claude's):
cp -R ./sales-report-skill ~/.copilot/skills/sales-report-skill

# GitHub Copilot (project-level):
cp -R ./sales-report-skill .github/skills/sales-report-skill

# Cursor (project-level ONLY — no global path exists):
cp -R ./sales-report-skill .cursor/skills/sales-report-skill

# Gemini CLI (native path):
cp -R ./sales-report-skill ~/.gemini/skills/sales-report-skill
```

**After installing, run a safe representative use case before claiming success.**
Use supplied material or a local golden fixture. Use dry-run or sandbox behavior for
skills that can send messages, publish, purchase, or write production data. If a safe
run needs credentials, data, or authority, report `verification-blocked` with one
exact setup action.

For a verified skill, tell the user exactly what now works:

```
The weekly sales report now works from a CRM export.

Result: ./output/weekly-sales-report.pdf

To use it, open a new session and type:

  /sales-report-skill Generate the weekly report for the West region

Checks: validation passed · pipeline passed · security scan clean · representative run passed

If the result is wrong:
  python3 ./sales-report-skill/scripts/evolve.py --correct "what it got wrong"
```

If you cannot detect the platform, show the user how to run the install manually:

```
I couldn't auto-detect your platform. To install, run:

  ./sales-report-skill/install.sh

Or specify your platform:

  ./sales-report-skill/install.sh --platform cursor

Or install to all detected platforms at once:

  ./sales-report-skill/install.sh --all

Alternative (if npx is available):

  npx skills add ./sales-report-skill
```

The `install.sh` inside the skill handles auto-detection, platform-specific paths, project vs user level, dry-run mode, and post-install activation instructions. It is the fallback for users who receive the skill as a package (not created in their current session).

The generated skill must be a self-contained package that anyone can install with `git clone` or `./install.sh` and invoke with `/skill-name` — the same way agent-skills-platform itself works.

## Share With Your Team (Post-Creation)

After the representative result is visible and the user has had a chance to judge it,
ask:

```
Want to share this skill with your team so they can install it too?
```

Corporate users don't know what a registry is, how to `git push`, or what `skill_registry.py` does. They just want their colleague to have the same skill. You handle everything.

**If the user says yes, do all of this automatically:**

1. **Initialize a git repo** inside the generated skill directory:
   ```bash
   cd ./sales-report-skill
   git init
   git add -A
   git commit -m "feat: Initial skill — sales-report-skill"
   ```

2. **Detect the team's git platform** and create a remote repo:

   Check which CLI tools are available and authenticated:

   ```
   gh auth status    → GitHub (github.com or GitHub Enterprise)
   glab auth status  → GitLab (gitlab.com or self-hosted)
   ```

   **If `gh` is available (GitHub):**
   ```bash
   gh repo create sales-report-skill --public --source=. --push
   gh repo edit --add-topic agent-skill
   ```

   **If `glab` is available (GitLab):**
   ```bash
   glab repo create sales-report-skill --public --defaultBranch main
   git remote add origin <returned-url>
   git push -u origin main
   glab repo edit --topic agent-skill
   ```

   The `agent-skill` topic makes skills discoverable across the org. Teams can search `topic:agent-skill` on GitHub or filter by topic on GitLab to find all shared skills.

   **If both are available**, check the existing git remotes in the current project to infer which platform the team uses. If the current project's `origin` points to `gitlab.com` or a GitLab instance, use `glab`. Otherwise default to `gh`.

   **If neither is available**, tell the user:
   ```
   I can't create the repo automatically. To share this skill:
   1. Create a new repo on GitHub or GitLab called "sales-report-skill"
   2. Then run:
      git remote add origin <repo-url>
      git push -u origin main
   3. Share the git clone link with your team
   ```

3. **Give the user a shareable one-liner** they can send to colleagues:
   ```
   Shared! Your colleagues can install it by pasting this in their terminal:

     git clone <repo-url> ~/.claude/skills/sales-report-skill

   Or for VS Code Copilot:

     git clone <repo-url> .github/skills/sales-report-skill

   Or for Cursor:

     git clone <repo-url> .cursor/rules/sales-report-skill
   ```

   Use the actual repo URL from step 2 (GitHub or GitLab). The install pattern is identical regardless of git platform.

4. **Optionally publish to the team registry** (if the agent-skills-platform registry is available):
   ```bash
   python3 scripts/skill_registry.py publish ./sales-report-skill/ --tags <auto-generated-tags>
   ```

The goal: the user who created the skill sends a one-liner to their colleague on Slack or Teams. The colleague pastes it. Done. No registry knowledge, no `skill_registry.py`, no understanding of the spec. Just `git clone` and it works — whether the team uses GitHub or GitLab.

**If the user says no**, that's fine — the skill is already installed locally and working. They can always share later.

## Set Up a Lightweight Cross-Git Registry

Use this legacy-compatible path when the team needs GitLab support, works across
several agent clients, or does not have GitHub CLI 2.90+ with `gh skill`. For a
GitHub organization centered on VS Code Copilot Agent Mode, use the governed
marketplace above instead.

For the complete GitLab command sequence, follow
[`docs/GITLAB_TEAM_REGISTRY.md`](../docs/GITLAB_TEAM_REGISTRY.md). Do not imply
that the lightweight registry has schema-v2 bundles, generated GitLab CI, or
native `gh skill` installation.

The lightweight registry is a shared Git repository that acts as a catalog where
team members publish and copy-install skills. It provides version history and
repository permissions, but it does not generate bundle manifests, CODEOWNERS,
protected release workflows, or immutable managed installs.

This is the model for AI consultants enabling corporate teams:
1. The consultant teaches each team member to install and use agent-skills-platform
2. The consultant creates one shared `{team}-skills-registry` repo on GitHub/GitLab
3. Each team member creates skills from their own workflows using `/agent-skills-platform`
4. Each member publishes to the shared registry
5. Other members browse, search, and install from that same registry

The consultant delivers **knowledge and infrastructure**, not skills. The team creates the skills themselves — they know their workflows better than anyone.

```
Want me to set up a shared skill registry for your team? It's a single
repo where everyone publishes their skills and anyone can browse and
install them — like an internal app store for agent skills.
```

**If the user says yes, do all of this automatically:**

1. **Ask for the team or org name** to use in the registry name (e.g., "engineering", "acme-corp"):

2. **Initialize the registry**:
   ```bash
   mkdir -p ~/{team}-skills-registry
   python3 scripts/skill_registry.py init --registry ~/{team}-skills-registry --name "{Team Name} Skills"
   ```

3. **Create a remote repo** (same GitHub/GitLab detection as skill sharing):
   ```bash
   cd ~/{team}-skills-registry
   git init && git add -A && git commit -m "feat: Initialize {team} skill registry"

   # GitHub
   gh repo create {team}-skills-registry --private --source=. --push
   gh repo edit --add-topic agent-skill-registry

   # Or GitLab
   glab repo create {team}-skills-registry --private --defaultBranch main
   git remote add origin <url> && git push -u origin main
   ```

   The registry repo should be **private** by default (internal to the org). The team admin controls who has access via GitHub/GitLab repo permissions.

4. **If a skill was just created**, publish it as the first entry:
   ```bash
   python3 scripts/skill_registry.py publish ./sales-report-skill/ --registry ~/{team}-skills-registry --tags sales,reports
   cd ~/{team}-skills-registry && git add -A && git commit -m "feat: Add sales-report-skill" && git push
   ```

5. **Give the user a team onboarding guide** they can share on Slack, Teams, or email:

   ```
   Registry is live! Share this with your team:

   ──────────────────────────────────────────────
   TEAM SKILL REGISTRY — Quick Start
   ──────────────────────────────────────────────

   STEP 1: Install agent-skills-platform (one time)

     git clone https://github.com/FrancyJGLisboa/agent-skills-platform.git ~/.claude/skills/agent-skills-platform

     For VS Code Copilot:
       git clone https://github.com/FrancyJGLisboa/agent-skills-platform.git .github/skills/agent-skills-platform

     For Cursor:
       git clone https://github.com/FrancyJGLisboa/agent-skills-platform.git .cursor/rules/agent-skills-platform

   STEP 2: Clone the team registry (one time)

     git clone <registry-repo-url> ~/{team}-skills-registry

   STEP 3: Create a skill from any workflow you do repeatedly

     Open your IDE chat and type:
       /agent-skills-platform Every week I pull sales data and generate a report

   STEP 4: Publish your skill to the team registry

     python3 scripts/skill_registry.py publish ./my-skill/ --registry ~/{team}-skills-registry --tags tag1,tag2
     cd ~/{team}-skills-registry && git add -A && git commit -m "Add my-skill" && git push

   STEP 5: Install a colleague's skill

     git pull (inside ~/{team}-skills-registry to get latest)
     python3 scripts/skill_registry.py list --registry ~/{team}-skills-registry
     python3 scripts/skill_registry.py search "sales" --registry ~/{team}-skills-registry
     python3 scripts/skill_registry.py install sales-report-skill --registry ~/{team}-skills-registry

   STEP 6: Manage what is installed (tracked in ~/.agent-skills/installed.json)

     python3 scripts/skill_registry.py installed                    # what is installed where
     python3 scripts/skill_registry.py update --all --check         # exit 2 if the registry moved on
     python3 scripts/skill_registry.py update --all                 # reinstall outdated skills
     python3 scripts/skill_registry.py disable sales-report-skill   # park it outside the tool's tree
     python3 scripts/skill_registry.py enable sales-report-skill    # put it back
     python3 scripts/skill_registry.py uninstall sales-report-skill --force   # to the recycle bin
     python3 scripts/skill_registry.py restore sales-report-skill   # back from the recycle bin
     python3 scripts/skill_registry.py purge                        # drop bin items older than 30 days

     Every lifecycle command also takes --tag <tag> or --all instead of a name,
     so `disable --tag sales` parks every sales skill at once.

   ──────────────────────────────────────────────
   ```

**When to use this registry:**
- The organization uses GitLab or another Git host instead of GitHub.
- The team needs the existing copy-based 17-platform installer.
- `gh skill` preview is unavailable or not approved.

**When NOT to offer:**
- User is creating a single personal skill
- A registry already exists (check for `~/team-skills-registry` or similar)
- The team requested governed GitHub Copilot distribution; use
  `scripts/team_marketplace.py` for that case.

The registry is a git repo. Version history, access control, and review workflows come free from GitHub/GitLab. No servers, no databases, no new tools.

See `references/pipeline-phases.md` for detailed Phase 5 instructions.

## Update Check

When loading this skill, silently check if the local copy is behind the remote. Run:

```bash
cd <skill-install-dir> && git rev-parse HEAD 2>/dev/null
cd <skill-install-dir> && git ls-remote origin HEAD 2>/dev/null | cut -f1
```

If both commands succeed and the hashes differ, mention to the user:
"A newer version of agent-skills-platform is available. Run `git pull` in <path> to update."

Do not block or interrupt for this. If either command fails (no git, no network, not a git repo), skip silently.
