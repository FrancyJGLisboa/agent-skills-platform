// Human names for platform ids. Anything unknown falls back to the id itself.
export const PLATFORM_LABELS: Record<string, string> = {
  "github-copilot": "GitHub Copilot",
  "claude-code": "Claude Code",
  cursor: "Cursor",
  windsurf: "Windsurf",
  cline: "Cline",
  codex: "Codex CLI",
  gemini: "Gemini CLI",
  kiro: "Kiro",
  trae: "Trae",
  goose: "Goose",
  opencode: "OpenCode",
  "roo-code": "Roo Code",
  "kilo-code": "Kilo Code",
  factory: "Factory Droid",
  junie: "Junie",
  antigravity: "Antigravity",
  universal: "Universal (~/.agents)",
};
export const platformLabel = (id: string) => PLATFORM_LABELS[id] ?? id;
