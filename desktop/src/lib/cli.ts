// Typed wrapper over the Rust `registry` bridge. Every call is one
// `skill_registry.py <args> --json` invocation; nothing is cached here.
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

export interface Settings {
  /** Git URL of the team library (a repo with registry.json). Empty = none. */
  libraryUrl: string;
  /** Local registry directory. Set by library sync, or by hand in Advanced. */
  registry: string;
  /** Default install target; github-copilot for the Copilot-first release. */
  platform: string;
  /** Working directory for project-scope installs. Advanced. */
  projectDir: string;
  /** Advanced: run skill_registry.py from a checkout instead of the bundled sidecar. */
  scriptsDir: string;
  python: string;
}

export const DEFAULT_SETTINGS: Settings = {
  libraryUrl: "", registry: "", platform: "github-copilot", projectDir: "", scriptsDir: "", python: "python3",
};

export interface PlatformInfo {
  name: string;
  user_path: string;
  project_path: string;
  detected: boolean;
}

export interface LibraryInfo {
  url: string;
  name: string;
  path: string;
  commit: string;
  branch: string;
  /** Unix seconds. */
  synced_at: string;
}

export interface CliResult<T = unknown> {
  code: number;
  data: T | null;
  stdout: string;
  stderr: string;
}

export interface InstalledSkill {
  name: string;
  author: string;
  version: string;
  platform: string;
  scope: "user" | "project";
  path: string;
  registry: string;
  tags: string[];
  installed_at: string;
  enabled: boolean;
  parked_path?: string;
}

export interface RegistrySkill {
  name: string;
  description: string;
  version: string;
  author: string;
  license: string;
  tags: string[];
  platforms: string[];
  published: string;
  path: string;
  validation?: { valid: boolean; errors: number; warnings: number };
  security?: { clean: boolean; issues: number };
}

export interface UpdateResult {
  name: string;
  platform: string;
  path: string;
  installed: string;
  available: string | null;
  status: string;
}

export interface TrashItem {
  kind: "install" | "registry";
  name: string;
  trashed_at: string;
  origin: string;
  item: string;
}

export interface StaleResult {
  name: string;
  version: string;
  status: string;
  days_since_review: number | null;
}

const SETTINGS_KEY = "agent-skills-desktop.settings";

export function loadSettings(): Settings | null {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    // Older saves lack libraryUrl; fill defaults so every field is a string.
    return raw ? { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) } : null;
  } catch {
    return null;
  }
}

/** True once the app can do something useful: a library or a registry folder. */
export const isConfigured = (s: Settings | null): s is Settings => !!s && (!!s.registry || !!s.libraryUrl);

export function saveSettings(settings: Settings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Per-viewer convenience only; a failed save just means re-entering paths next launch.
  }
}

export async function defaultScriptsDir(): Promise<string> {
  return invoke<string>("default_scripts_dir");
}

export async function listPlatforms(settings: Pick<Settings, "python" | "scriptsDir">): Promise<PlatformInfo[]> {
  return invoke<PlatformInfo[]>("platforms", { python: settings.python || null, scriptsDir: settings.scriptsDir || null });
}

export async function run<T = unknown>(settings: Settings, args: string[]): Promise<CliResult<T>> {
  return invoke<CliResult<T>>("registry", {
    python: settings.python || null,
    scriptsDir: settings.scriptsDir || null,
    cwd: settings.projectDir || null,
    args,
  });
}

export const library = {
  sync: (url: string) => invoke<LibraryInfo>("library_sync", { url }),
  status: (url: string) => invoke<LibraryInfo | null>("library_status", { url }),
  hasRegistry: (path: string) => invoke<boolean>("library_has_registry", { path }),
  setToken: (url: string, token: string) => invoke<void>("library_set_token", { url, token }),
  hasToken: (url: string) => invoke<boolean>("library_has_token", { url }),
};

/** Throw a readable error when the CLI failed, so callers can show it once. */
export function expectOk<T>(result: CliResult<T>, okCodes: number[] = [0]): T {
  if (!okCodes.includes(result.code)) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || `exit code ${result.code}`);
  }
  return result.data as T;
}

const reg = (s: Settings) => ["--registry", s.registry];

export const api = {
  installed: (s: Settings) => run<InstalledSkill[]>(s, ["installed"]).then((r) => expectOk(r)),
  registryList: (s: Settings) => run<RegistrySkill[]>(s, ["list", ...reg(s)]).then((r) => expectOk(r)),
  stale: (s: Settings) => run<StaleResult[]>(s, ["stale", ...reg(s)]).then((r) => expectOk(r)),
  trash: (s: Settings) => run<TrashItem[]>(s, ["trash"]).then((r) => expectOk(r)),
  checkUpdates: (s: Settings) =>
    run<UpdateResult[]>(s, ["update", "--all", "--check"]).then((r) => expectOk(r, [0, 2])),
  update: (s: Settings, name: string, platform: string) =>
    run<UpdateResult[]>(s, ["update", name, "--platform", platform]).then((r) => expectOk(r)),
  updateAll: (s: Settings) => run<UpdateResult[]>(s, ["update", "--all"]).then((r) => expectOk(r)),
  enable: (s: Settings, name: string, platform: string) =>
    run(s, ["enable", name, "--platform", platform]).then((r) => expectOk(r)),
  disable: (s: Settings, name: string, platform: string) =>
    run(s, ["disable", name, "--platform", platform]).then((r) => expectOk(r)),
  uninstall: (s: Settings, name: string, platform: string) =>
    run(s, ["uninstall", name, "--platform", platform, "--force"]).then((r) => expectOk(r)),
  install: (s: Settings, name: string, scope: "user" | "project", force: boolean) =>
    run(s, [
      "install", name, ...reg(s), "--platform", s.platform,
      ...(scope === "project" ? ["--project"] : []),
      ...(force ? ["--force"] : []),
    ]).then((r) => expectOk(r)),
  installTag: (s: Settings, tag: string, scope: "user" | "project") =>
    run(s, [
      "install", "--tag", tag, ...reg(s), "--platform", s.platform,
      ...(scope === "project" ? ["--project"] : []),
    ]).then((r) => expectOk(r)),
  restore: (s: Settings, name: string, force: boolean) =>
    run(s, ["restore", name, ...(force ? ["--force"] : [])]).then((r) => expectOk(r)),
  purge: (s: Settings, olderThan: number) =>
    run<TrashItem[]>(s, ["purge", "--older-than", String(olderThan)]).then((r) => expectOk(r)),
};

export interface FileEntry {
  path: string;
  size: number;
}

export async function skillFiles(dir: string): Promise<FileEntry[]> {
  return invoke<FileEntry[]>("skill_files", { dir });
}

export async function skillFile(dir: string, file: string): Promise<string> {
  return invoke<string>("skill_file", { dir, file });
}

/** Native folder picker; resolves to null when the user cancels. */
export async function pickDirectory(title: string, defaultPath?: string): Promise<string | null> {
  const picked = await open({ directory: true, multiple: false, title, defaultPath: defaultPath || undefined });
  return typeof picked === "string" ? picked : null;
}

/** Registry `info` for one skill — the detail drawer's metadata source. */
export async function registryInfo(s: Settings, name: string): Promise<RegistrySkill> {
  return run<RegistrySkill>(s, ["info", name, "--registry", s.registry]).then((r) => expectOk(r));
}
