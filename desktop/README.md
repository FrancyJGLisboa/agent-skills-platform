# Agent Skills desktop app

A Tauri 2 + React front end for `scripts/skill_registry.py`. It shows what is
installed on this machine, what a registry offers, and what is in the recycle
bin, with the same enable / disable / update / uninstall / restore actions the
CLI provides.

The app holds no registry logic. Every action runs
`python3 <scripts>/skill_registry.py <command> --json` and renders the result,
so the CLI stays the single source of truth and anything it can do the app can
show.

## For teammates (no tools required)

Download the installer for your OS from the latest **Agent Skills desktop**
release, open it, and paste the team-library link your admin sent you. That
is all: the app bundles the skill CLI, keeps a copy of the library up to
date, and installs skills into GitHub Copilot (or another tool you pick) with
one click. It checks for its own updates on launch.

Private library? Open "Private repository? Add an access token" under the
link and paste a personal access token with read access. It is stored in
your system keychain.

## For contributors

- Node 18+, Rust stable, Python 3.10+ with `uv` (for the sidecar build), and
  Tauri's platform prerequisites (<https://tauri.app/start/prerequisites/>)

```bash
cd desktop
npm install
npm run sidecar       # bundles ../scripts/skill_registry.py into src-tauri/binaries/
npm run tauri dev
```

The sidecar must exist before any cargo step: Tauri refuses to build without
its `externalBin`. Rebuild it after changing anything under `scripts/`.

To run against a checkout instead of the bundled copy (so edits to the Python
show up without rebuilding the sidecar), open Settings → Advanced → "Run from
a checkout" and click Detect.

## Releasing

1. Bump `version` in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, and `package.json`.
2. Tag `desktop-vX.Y.Z` and push the tag. `.github/workflows/desktop-release.yml`
   builds macOS (Apple Silicon and Intel), Windows, and Linux installers and opens a draft release.
3. Publish the draft. Installed apps offer the update on next launch.

Secrets the release workflow uses (all optional; without them the builds are
unsigned and the updater is disabled):

| Secret | Purpose |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` (+ `_PASSWORD`) | Signs updater artifacts. The matching public key is in `tauri.conf.json`; the private key lives in `~/.tauri/agent-skills-updater.key` on the machine that generated it. |
| `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY` | macOS code signing (Developer ID Application, base64-encoded .p12). |
| `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` | macOS notarization (app-specific password). |

Windows Authenticode signing is not wired yet; SmartScreen will warn on
first launch until it is.

## Layout

```
src/lib/cli.ts           typed wrapper over the Rust bridge, one function per CLI command
src/components/ui.tsx    Button, Input, Select, Pill, Switch, Field, PageHeader, Empty, TagChips, PathText
src/components/          Sidebar, Installed, Registry, Trash, SettingsView, SkillDrawer
src/index.css            Tailwind import, colour tokens (light + dark), SKILL.md prose styles
src-tauri/src/lib.rs     registry(args) [sidecar or checkout], platforms(), skill_files/skill_file, library_* commands
src-tauri/src/library.rs Git clone/fast-forward of the team library (vendored libgit2) + keychain token
scripts/build-sidecar.mjs PyInstaller bundle of ../scripts/skill_registry.py
```

Styling is Tailwind 4 with a small token set in `src/index.css`; icons are
Lucide; toasts are Sonner; `SKILL.md` renders through react-markdown. The two
file commands only read inside a skill directory the UI already knows about,
capped at 512 KiB per file, so the detail drawer can show the file tree and
any text file without a second code path.

Settings persist in the WebView's `localStorage`; the installed-skill ledger,
parked disabled skills, and the recycle bin live in `~/.agent-skills/` (or
`$AGENT_SKILLS_HOME`), exactly as for the CLI.
