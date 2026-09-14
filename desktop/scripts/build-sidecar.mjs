#!/usr/bin/env node
// Bundle scripts/skill_registry.py into a single executable Tauri can ship as a sidecar.
//
// Tauri looks for sidecars as <name>-<target-triple>[.exe] next to tauri.conf.json's
// externalBin entry, so the output lands at src-tauri/binaries/skill_registry-<triple>.
// PyInstaller is run through uvx when available, else `python -m PyInstaller`.
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");
const scripts = path.join(repo, "scripts");
const out = path.join(here, "../src-tauri/binaries");

const triple = process.env.TAURI_TARGET_TRIPLE || execFileSync("rustc", ["-vV"], { encoding: "utf8" }).match(/host: (\S+)/)[1];
const name = `skill_registry-${triple}`;
const python = process.env.PYTHON || "python3";

const args = [
  "--onefile", "--clean", "--noconfirm",
  "--name", name,
  "--distpath", out,
  "--workpath", path.join(here, "../.pyinstaller/build"),
  "--specpath", path.join(here, "../.pyinstaller"),
  "--paths", scripts,
  // Sibling modules are imported by name at runtime; make sure they are collected.
  ...["validate", "skill_document", "security_scan", "review_staleness", "platforms", "installed_skills",
      "marketplace_discovery", "structured_interview"].flatMap((m) => ["--hidden-import", m]),
  path.join(scripts, "skill_registry.py"),
];

mkdirSync(out, { recursive: true });
const runners = [
  ["uvx", ["--from", "pyinstaller", "pyinstaller", ...args]],
  [python, ["-m", "PyInstaller", ...args]],
];
let ok = false;
for (const [cmd, a] of runners) {
  const r = spawnSync(cmd, a, { stdio: "inherit" });
  if (r.status === 0) { ok = true; break; }
  if (r.error?.code !== "ENOENT") process.exit(r.status ?? 1);
}
if (!ok) { console.error("PyInstaller not found: install uv (uvx) or `pip install pyinstaller`."); process.exit(1); }

const built = path.join(out, process.platform === "win32" ? `${name}.exe` : name);
if (!existsSync(built)) { console.error(`expected ${built}`); process.exit(1); }
rmSync(path.join(here, "../.pyinstaller"), { recursive: true, force: true });
console.log(`sidecar: ${built}`);
