# Agent Skills desktop app

A Tauri 2 + React front end for `scripts/skill_registry.py`. It shows what is
installed on this machine, what a registry offers, and what is in the recycle
bin, with the same enable / disable / update / uninstall / restore actions the
CLI provides.

The app holds no registry logic. Every action runs
`python3 <scripts>/skill_registry.py <command> --json` and renders the result,
so the CLI stays the single source of truth and anything it can do the app can
show.

## Requirements

- A checkout of agent-skills-platform (the app needs its `scripts/` directory)
- Python 3.10+ on `PATH` (or set the executable in Settings)
- To build: Node 18+, Rust stable, and Tauri's platform prerequisites
  (<https://tauri.app/start/prerequisites/>)

## Run

```bash
cd desktop
npm install
npm run tauri dev
```

First launch opens Settings. The `scripts/` directory is pre-filled when the
app can find one (`$AGENT_SKILLS_PLATFORM/scripts`, the repo it was built from,
or a global install under `~/.claude/skills`, `~/.agents/skills`,
`~/.copilot/skills`). Point it at a registry directory (one that contains
`registry.json`) and pick the default platform for installs.

## Build a bundle

```bash
npm run tauri build            # every bundle type for this OS
npm run tauri build -- --bundles app   # macOS .app only
```

Output lands under `src-tauri/target/release/bundle/`.

## Layout

```
src/lib/cli.ts           typed wrapper over the Rust bridge, one function per CLI command
src/components/          Installed, Registry, Trash, SettingsView, TagFilter
src-tauri/src/lib.rs     three commands: registry(args), platforms(), default_scripts_dir()
```

Settings persist in the WebView's `localStorage`; the installed-skill ledger,
parked disabled skills, and the recycle bin live in `~/.agent-skills/` (or
`$AGENT_SKILLS_HOME`), exactly as for the CLI.
