import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ChevronRight, FolderOpen, KeyRound, Link2, Loader2 } from "lucide-react";
import { clsx } from "clsx";
import { DEFAULT_SETTINGS, defaultScriptsDir, library, LibraryInfo, listPlatforms, pickDirectory, PlatformInfo, Settings } from "../lib/cli";
import { Button, Field, Input, PageHeader, Pill, Select } from "./ui";
import { platformLabel } from "../lib/platforms";
import { checkForUpdates } from "../lib/updates";
import { getVersion } from "@tauri-apps/api/app";

interface Props {
  initial: Settings | null;
  onSave: (settings: Settings) => void;
}

const label = (p: PlatformInfo) => (p.name === "github-copilot" ? "GitHub Copilot (VS Code)" : platformLabel(p.name));

export function SettingsView({ initial, onSave }: Props) {
  const [form, setForm] = useState<Settings>(initial ?? DEFAULT_SETTINGS);
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [lib, setLib] = useState<LibraryInfo | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [token, setToken] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [version, setVersion] = useState("");
  useEffect(() => { getVersion().then(setVersion).catch(() => setVersion("dev")); }, []);
  const [advanced, setAdvanced] = useState(!!(initial?.scriptsDir || initial?.projectDir || (initial?.registry && !initial?.libraryUrl)));

  const set = (key: keyof Settings) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => {
    listPlatforms(form).then(setPlatforms).catch((e) => toast.error("Could not list install targets", { description: String(e) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.scriptsDir, form.python]);

  useEffect(() => {
    if (!form.libraryUrl) { setLib(null); setHasToken(false); return; }
    library.status(form.libraryUrl).then(setLib).catch(() => setLib(null));
    library.hasToken(form.libraryUrl).then(setHasToken).catch(() => setHasToken(false));
  }, [form.libraryUrl]);

  const connect = async () => {
    const url = form.libraryUrl.trim();
    if (!url) return;
    setConnecting(true);
    try {
      if (token) {
        await library.setToken(url, token);
        setToken("");
        setHasToken(true);
      }
      const info = await library.sync(url);
      if (!(await library.hasRegistry(info.path))) {
        toast.error("That repository has no registry.json", { description: "Ask the library admin for the team-library URL." });
        return;
      }
      setLib(info);
      setForm((f) => ({ ...f, libraryUrl: url, registry: info.path }));
      toast.success(`Connected to ${info.name}`, { description: `${info.branch} @ ${info.commit}` });
    } catch (e) {
      toast.error("Could not connect", { description: String(e) });
    } finally {
      setConnecting(false);
    }
  };

  const browse = (key: "registry" | "projectDir" | "scriptsDir", title: string) => async () => {
    const dir = await pickDirectory(title, form[key]);
    if (dir) set(key)(dir);
  };

  const canSave = !!(form.registry || form.libraryUrl) && !connecting;
  const detected = platforms.filter((p) => p.detected);
  const others = platforms.filter((p) => !p.detected);

  return (
    <>
      <PageHeader title="Settings" />
      <div className="mx-auto max-w-xl px-6 py-6">
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-1 flex items-center gap-2 text-[14px] font-semibold"><Link2 size={15} className="text-accent" /> Team library</h2>
          <p className="mb-4 text-ink-2">Paste the link your admin sent you. The app keeps a copy up to date on this computer.</p>
          <Field label="Library link">
            <div className="flex gap-2">
              <Input value={form.libraryUrl} onChange={(e) => set("libraryUrl")(e.target.value)} placeholder="https://github.com/your-org/team-skills" spellCheck={false} autoFocus={!initial}
                onKeyDown={(e) => e.key === "Enter" && connect()} />
              <Button variant="primary" onClick={connect} loading={connecting} disabled={!form.libraryUrl.trim()}>{lib ? "Update" : "Connect"}</Button>
            </div>
          </Field>
          {lib && (
            <p className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-ink-2">
              <CheckCircle2 size={14} className="text-ok" /> Connected to <strong className="text-ink">{lib.name}</strong>
              <Pill>{lib.branch} @ {lib.commit}</Pill>
            </p>
          )}
          <details className="mt-4 group">
            <summary className="flex cursor-pointer list-none items-center gap-1 text-[12px] text-ink-2 hover:text-ink">
              <ChevronRight size={13} className="transition-transform group-open:rotate-90" /> Private repository? Add an access token
              {hasToken && <Pill tone="ok">token saved</Pill>}
            </summary>
            <div className="mt-3 flex gap-2">
              <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={hasToken ? "Replace saved token" : "Personal access token"} spellCheck={false} />
              <Button onClick={async () => { await library.setToken(form.libraryUrl, token); setHasToken(!!token); setToken(""); toast.success(token ? "Token saved to your keychain" : "Token removed"); }} disabled={!form.libraryUrl.trim() || (!token && !hasToken)}>
                <KeyRound size={14} /> {token ? "Save" : hasToken ? "Remove" : "Save"}
              </Button>
            </div>
            <p className="mt-1.5 text-[12px] text-ink-3">Stored in the system keychain, never in the app. Needs read access to the repository.</p>
          </details>
        </section>

        <section className="mt-5 rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-1 text-[14px] font-semibold">Install skills for</h2>
          <p className="mb-4 text-ink-2">Where skills go when you click Install. Tools found on this computer are listed first.</p>
          <Select value={form.platform} onChange={(e) => set("platform")(e.target.value)} className="w-full">
            {detected.length > 0 && <optgroup label="On this computer">{detected.map((p) => <option key={p.name} value={p.name}>{label(p)}</option>)}</optgroup>}
            {others.length > 0 && <optgroup label="Other tools">{others.map((p) => <option key={p.name} value={p.name}>{label(p)}</option>)}</optgroup>}
            {platforms.length === 0 && <option value={form.platform}>{platformLabel(form.platform)}</option>}
          </Select>
          {form.platform === "github-copilot" && (
            <p className="mt-2 text-[12px] text-ink-3">Installed skills land in <code className="font-mono">~/.copilot/skills</code>. Restart VS Code, then use them in Copilot Chat agent mode.</p>
          )}
        </section>

        <button onClick={() => setAdvanced((a) => !a)} className="mt-5 flex items-center gap-1 text-[12px] text-ink-2 hover:text-ink">
          <ChevronRight size={13} className={clsx("transition-transform", advanced && "rotate-90")} /> Advanced
        </button>
        {advanced && (
          <section className="mt-3 space-y-4 rounded-lg border border-dashed border-line p-5">
            <Field label="Local registry folder" hint="Use a registry already on disk instead of a team library.">
              <div className="flex gap-2">
                <Input value={form.registry} onChange={(e) => set("registry")(e.target.value)} placeholder="~/team-skills-registry" spellCheck={false} />
                <Button onClick={browse("registry", "Registry folder")}><FolderOpen size={14} /> Browse</Button>
              </div>
            </Field>
            <Field label="Project folder" hint="Enables project-scope installs (skills that apply to one repository).">
              <div className="flex gap-2">
                <Input value={form.projectDir} onChange={(e) => set("projectDir")(e.target.value)} placeholder="(optional)" spellCheck={false} />
                <Button onClick={browse("projectDir", "Project folder")}><FolderOpen size={14} /> Browse</Button>
              </div>
            </Field>
            <Field label="Run from a checkout" hint="For contributors: use scripts/skill_registry.py from a checkout instead of the bundled copy.">
              <div className="flex gap-2">
                <Input value={form.scriptsDir} onChange={(e) => set("scriptsDir")(e.target.value)} placeholder="/path/to/agent-skills-platform/scripts" spellCheck={false} />
                <Button onClick={browse("scriptsDir", "scripts directory")}><FolderOpen size={14} /> Browse</Button>
                <Button onClick={async () => { const d = await defaultScriptsDir(); if (d) set("scriptsDir")(d); else toast.info("No checkout found"); }}>Detect</Button>
              </div>
            </Field>
            {form.scriptsDir && (
              <Field label="Python executable">
                <Input value={form.python} onChange={(e) => set("python")(e.target.value)} placeholder="python3" spellCheck={false} />
              </Field>
            )}
          </section>
        )}

        <div className="mt-6 flex items-center gap-2">
          <Button variant="primary" onClick={() => onSave(form)} disabled={!canSave}>{connecting ? <Loader2 size={14} className="animate-spin" /> : null} Save</Button>
          {!canSave && !connecting && <span className="text-[12px] text-ink-3">Connect a library first.</span>}
          <span className="ml-auto flex items-center gap-2 text-[12px] text-ink-3">
            Agent Skills {version}
            <Button size="sm" variant="ghost" onClick={() => checkForUpdates({ silent: false })}>Check for updates</Button>
          </span>
        </div>
      </div>
    </>
  );
}
