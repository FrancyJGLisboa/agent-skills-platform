import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, FolderOpen } from "lucide-react";
import { defaultScriptsDir, listPlatforms, pickDirectory, Settings } from "../lib/cli";
import { Button, Field, Input, PageHeader, Select } from "./ui";

interface Props {
  initial: Settings | null;
  onSave: (settings: Settings) => void;
}

const EMPTY: Settings = { python: "python3", scriptsDir: "", registry: "", projectDir: "", platform: "claude-code" };

export function SettingsView({ initial, onSave }: Props) {
  const [form, setForm] = useState<Settings>(initial ?? EMPTY);
  const [platforms, setPlatforms] = useState<string[]>([form.platform]);
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!initial?.scriptsDir) defaultScriptsDir().then((dir) => dir && setForm((f) => ({ ...f, scriptsDir: dir })));
  }, [initial]);

  const set = (key: keyof Settings) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const browse = (key: "scriptsDir" | "registry" | "projectDir", title: string) => async () => {
    const dir = await pickDirectory(title, form[key]);
    if (dir) set(key)(dir);
  };

  const check = async () => {
    setChecking(true);
    setStatus(null);
    try {
      const list = await listPlatforms(form);
      setPlatforms(list);
      setStatus(`${list.length} platforms available`);
      return true;
    } catch (e) {
      toast.error("Could not reach skill_registry.py", { description: String(e) });
      return false;
    } finally {
      setChecking(false);
    }
  };

  const save = async () => {
    if (await check()) onSave(form);
  };

  const dirField = (key: "scriptsDir" | "registry" | "projectDir", placeholder: string, title: string) => (
    <div className="flex gap-2">
      <Input value={form[key]} onChange={(e) => set(key)(e.target.value)} placeholder={placeholder} spellCheck={false} />
      <Button onClick={browse(key, title)} aria-label={`Browse for ${title}`}><FolderOpen size={14} /> Browse</Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Settings" />
      <div className="mx-auto max-w-xl px-6 py-6">
        <p className="mb-6 text-ink-2">
          This app is a front end for <code className="font-mono text-[12px]">scripts/skill_registry.py</code>. Point it at a checkout of
          agent-skills-platform and a registry directory; everything else is read from there.
        </p>

        <div className="space-y-5">
          <Field label="Platform scripts directory" hint="The scripts/ folder inside a checkout or global install of agent-skills-platform.">
            {dirField("scriptsDir", "/path/to/agent-skills-platform/scripts", "Platform scripts directory")}
          </Field>
          <Field label="Registry directory" hint="A directory containing registry.json. Leave empty to manage installed skills only.">
            {dirField("registry", "~/team-skills-registry", "Registry directory")}
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Default platform for installs">
              <Select value={form.platform} onChange={(e) => set("platform")(e.target.value)} className="w-full">
                {(platforms.includes(form.platform) ? platforms : [form.platform, ...platforms]).map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>
            </Field>
            <Field label="Python executable">
              <Input value={form.python} onChange={(e) => set("python")(e.target.value)} placeholder="python3" spellCheck={false} />
            </Field>
          </div>
          <Field label="Project directory" hint="Working directory for project-scope installs. Optional.">
            {dirField("projectDir", "(user-scope installs only)", "Project directory")}
          </Field>
        </div>

        <div className="mt-8 flex items-center gap-2">
          <Button onClick={check} loading={checking}>Check connection</Button>
          <Button variant="primary" onClick={save} disabled={checking || !form.scriptsDir}>Save</Button>
          {status && <span className="ml-2 inline-flex items-center gap-1 text-ok"><CheckCircle2 size={14} /> {status}</span>}
        </div>
      </div>
    </>
  );
}
