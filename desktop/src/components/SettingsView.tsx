import { useEffect, useState } from "react";
import { defaultScriptsDir, listPlatforms, Settings } from "../lib/cli";

interface Props {
  initial: Settings | null;
  onSave: (settings: Settings) => void;
  onError: (message: string) => void;
}

const EMPTY: Settings = { python: "python3", scriptsDir: "", registry: "", projectDir: "", platform: "claude-code" };

export function SettingsView({ initial, onSave, onError }: Props) {
  const [form, setForm] = useState<Settings>(initial ?? EMPTY);
  const [platforms, setPlatforms] = useState<string[]>([EMPTY.platform]);
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!initial?.scriptsDir) {
      defaultScriptsDir().then((dir) => dir && setForm((f) => ({ ...f, scriptsDir: dir })));
    }
  }, [initial]);

  const set = (key: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const check = async () => {
    setChecking(true);
    setStatus(null);
    try {
      const list = await listPlatforms(form);
      setPlatforms(list);
      setStatus(`OK — ${list.length} platforms available from ${form.scriptsDir}`);
      return true;
    } catch (e) {
      onError(`Could not reach skill_registry.py: ${String(e)}`);
      return false;
    } finally {
      setChecking(false);
    }
  };

  const save = async () => {
    if (await check()) onSave(form);
  };

  return (
    <section className="settings">
      <h2>Settings</h2>
      <p className="muted">
        The app is a front end for <code>scripts/skill_registry.py</code>; point it at a checkout of
        agent-skills-platform and a registry directory.
      </p>
      <label>
        Python executable
        <input value={form.python} onChange={set("python")} placeholder="python3" />
      </label>
      <label>
        Platform <code>scripts/</code> directory
        <input value={form.scriptsDir} onChange={set("scriptsDir")} placeholder="/path/to/agent-skills-platform/scripts" />
      </label>
      <label>
        Registry directory (contains <code>registry.json</code>)
        <input value={form.registry} onChange={set("registry")} placeholder="~/team-skills-registry" />
      </label>
      <label>
        Default platform for installs
        <select value={form.platform} onChange={set("platform")}>
          {(platforms.includes(form.platform) ? platforms : [form.platform, ...platforms]).map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </label>
      <label>
        Project directory for project-scope installs
        <input value={form.projectDir} onChange={set("projectDir")} placeholder="(leave empty for user-scope only)" />
      </label>
      <div className="actions">
        <button onClick={check} disabled={checking}>{checking ? "Checking…" : "Check connection"}</button>
        <button className="primary" onClick={save} disabled={checking || !form.scriptsDir}>Save</button>
      </div>
      {status && <p className="ok-text">{status}</p>}
    </section>
  );
}
