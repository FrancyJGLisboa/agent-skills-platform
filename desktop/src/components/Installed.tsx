import { useCallback, useEffect, useMemo, useState } from "react";
import { api, InstalledSkill, Settings, UpdateResult } from "../lib/cli";
import { TagChips, TagFilter, useTagFilter } from "./TagFilter";

interface Props {
  settings: Settings;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export function Installed({ settings, onError, onNotice }: Props) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [updates, setUpdates] = useState<Record<string, UpdateResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { tag, setTag, filtered } = useTagFilter(skills);

  const key = (s: { name: string; platform: string; path?: string }) => `${s.name}@${s.platform}`;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.installed(settings);
      setSkills(list);
      if (list.length) {
        const checks = await api.checkUpdates(settings);
        setUpdates(Object.fromEntries(checks.map((u) => [key(u), u])));
      } else {
        setUpdates({});
      }
    } catch (e) {
      onError(String(e));
    } finally {
      setLoading(false);
    }
  }, [settings, onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const act = async (label: string, skill: InstalledSkill, fn: () => Promise<unknown>) => {
    setBusy(key(skill));
    try {
      await fn();
      onNotice(`${label} ${skill.name} (${skill.platform})`);
      await refresh();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(null);
    }
  };

  const outdated = useMemo(
    () => Object.values(updates).filter((u) => u.status === "outdated").length,
    [updates],
  );

  return (
    <section>
      <header className="toolbar">
        <h2>Installed <span className="count">{skills.length}</span></h2>
        <TagFilter items={skills} tag={tag} setTag={setTag} />
        {outdated > 0 && (
          <button
            className="primary"
            disabled={busy !== null}
            onClick={async () => {
              setBusy("*");
              try {
                const results = await api.updateAll(settings);
                const n = results.filter((r) => r.status === "updated").length;
                onNotice(`Updated ${n} skill${n === 1 ? "" : "s"}`);
              } catch (e) {
                onError(String(e));
              } finally {
                setBusy(null);
                refresh();
              }
            }}
          >
            Update all ({outdated})
          </button>
        )}
        <button onClick={refresh} disabled={loading}>Refresh</button>
      </header>

      {loading && skills.length === 0 ? (
        <p className="muted">Reading ~/.agent-skills/installed.json…</p>
      ) : filtered.length === 0 ? (
        <p className="muted">
          {skills.length === 0
            ? "Nothing installed through skill_registry.py yet. Install one from the Registry tab."
            : `No installed skills carry tag “${tag}”.`}
        </p>
      ) : (
        <ul className="cards">
          {filtered.map((s) => {
            const u = updates[key(s)];
            const isBusy = busy === key(s) || busy === "*";
            return (
              <li key={s.path} className={`card ${s.enabled ? "" : "off"}`}>
                <div className="card-head">
                  <strong>{s.name}</strong>
                  <span className="version">{s.version}</span>
                  <span className={`pill ${s.enabled ? "on" : "off"}`}>{s.enabled ? "enabled" : "disabled"}</span>
                  {u?.status === "outdated" && <span className="pill warn">{u.available} available</span>}
                  {u?.status.startsWith("error") && <span className="pill err" title={u.status}>registry missing</span>}
                </div>
                <div className="meta">
                  <span>{s.platform}</span>
                  <span>{s.scope}</span>
                  <TagChips tags={s.tags} onPick={setTag} />
                </div>
                <code className="path" title={s.path}><span>{s.path}</span></code>
                <div className="actions">
                  {s.enabled ? (
                    <button disabled={isBusy} onClick={() => act("Disabled", s, () => api.disable(settings, s.name, s.platform))}>Disable</button>
                  ) : (
                    <button disabled={isBusy} onClick={() => act("Enabled", s, () => api.enable(settings, s.name, s.platform))}>Enable</button>
                  )}
                  <button
                    disabled={isBusy || u?.status !== "outdated"}
                    onClick={() => act("Updated", s, () => api.update(settings, s.name, s.platform))}
                  >
                    Update
                  </button>
                  <button
                    className="danger"
                    disabled={isBusy}
                    onClick={() => {
                      if (confirm(`Uninstall ${s.name} from ${s.platform}? It goes to the recycle bin.`)) {
                        act("Uninstalled", s, () => api.uninstall(settings, s.name, s.platform));
                      }
                    }}
                  >
                    Uninstall
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
