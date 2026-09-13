import { useCallback, useEffect, useState } from "react";
import { api, RegistrySkill, Settings, StaleResult } from "../lib/cli";
import { TagChips, TagFilter, useTagFilter } from "./TagFilter";

interface Props {
  settings: Settings;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onInstalled: () => void;
}

export function Registry({ settings, onError, onNotice, onInstalled }: Props) {
  const [skills, setSkills] = useState<RegistrySkill[]>([]);
  const [stale, setStale] = useState<Record<string, StaleResult>>({});
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"user" | "project">("user");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { tag, setTag, filtered } = useTagFilter(skills);

  const refresh = useCallback(async () => {
    if (!settings.registry) {
      setSkills([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [list, staleness] = await Promise.all([api.registryList(settings), api.stale(settings)]);
      setSkills(list);
      setStale(Object.fromEntries(staleness.map((s) => [s.name, s])));
    } catch (e) {
      onError(String(e));
    } finally {
      setLoading(false);
    }
  }, [settings, onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const visible = filtered.filter((s) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [s.name, s.description, s.author, s.tags.join(" ")].join(" ").toLowerCase().includes(q);
  });

  const install = async (name: string, force = false) => {
    setBusy(name);
    try {
      await api.install(settings, name, scope, force);
      onNotice(`Installed ${name} for ${settings.platform} (${scope})`);
      onInstalled();
    } catch (e) {
      const message = String(e);
      if (!force && message.includes("already installed") && confirm(`${name} is already installed there. Overwrite?`)) {
        await install(name, true);
        return;
      }
      onError(message);
    } finally {
      setBusy(null);
    }
  };

  const installTag = async () => {
    if (!tag) return;
    setBusy(`tag:${tag}`);
    try {
      await api.installTag(settings, tag, scope);
      onNotice(`Installed every “${tag}” skill for ${settings.platform} (${scope})`);
      onInstalled();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!settings.registry) {
    return <p className="muted">Set a registry path in Settings to browse and install skills.</p>;
  }

  return (
    <section>
      <header className="toolbar">
        <h2>Registry <span className="count">{skills.length}</span></h2>
        <input placeholder="Search name, description, tags…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <TagFilter items={skills} tag={tag} setTag={setTag} />
        <label className="filter">
          Scope
          <select value={scope} onChange={(e) => setScope(e.target.value as "user" | "project")}>
            <option value="user">user ({settings.platform})</option>
            <option value="project">project</option>
          </select>
        </label>
        {tag && (
          <button className="primary" disabled={busy !== null} onClick={installTag}>
            Install all “{tag}” ({filtered.length})
          </button>
        )}
        <button onClick={refresh} disabled={loading}>Refresh</button>
      </header>
      <p className="muted small">{settings.registry}</p>

      {loading && skills.length === 0 ? (
        <p className="muted">Reading registry.json…</p>
      ) : visible.length === 0 ? (
        <p className="muted">{skills.length === 0 ? "Registry is empty." : "No skills match."}</p>
      ) : (
        <ul className="cards">
          {visible.map((s) => {
            const st = stale[s.name];
            return (
              <li key={`${s.author}/${s.name}/${s.version}`} className="card">
                <div className="card-head">
                  <strong>{s.name}</strong>
                  <span className="version">{s.version}</span>
                  {s.author && <span className="muted">by {s.author}</span>}
                  {s.validation && (
                    <span className={`pill ${s.validation.valid ? "on" : "err"}`}>
                      {s.validation.valid ? "valid" : `${s.validation.errors} errors`}
                    </span>
                  )}
                  {s.security && (
                    <span className={`pill ${s.security.clean ? "on" : "err"}`}>
                      {s.security.clean ? "clean" : `${s.security.issues} issues`}
                    </span>
                  )}
                  {st && st.status !== "fresh" && st.status !== "unknown" && (
                    <span className={`pill ${st.status === "overdue" ? "err" : "warn"}`}>
                      review {st.status.replace("_", " ")}
                    </span>
                  )}
                </div>
                <p className="desc">{s.description}</p>
                <div className="meta">
                  <TagChips tags={s.tags} onPick={setTag} />
                </div>
                <div className="actions">
                  <button className="primary" disabled={busy !== null} onClick={() => install(s.name)}>
                    {busy === s.name ? "Installing…" : "Install"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
