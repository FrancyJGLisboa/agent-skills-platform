import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ArrowUpCircle, Boxes, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { clsx } from "clsx";
import { api, InstalledSkill, listPlatforms, PlatformInfo, Settings, UpdateResult } from "../lib/cli";
import { platformLabel } from "../lib/platforms";
import { Button, Empty, PageHeader, Pill, Select, TagChips } from "./ui";
import { DrawerSkill } from "./SkillDrawer";

interface Props {
  settings: Settings;
  onOpen: (skill: DrawerSkill) => void;
  onCount: (n: number) => void;
  onOutdated: (n: number) => void;
  tagFilter: string | null;
  setTagFilter: (t: string | null) => void;
}

/** One skill as the user thinks of it: a name, installed for one or more tools. */
interface Group {
  name: string;
  scope: "user" | "project";
  version: string;
  author: string;
  tags: string[];
  registry: string;
  installs: InstalledSkill[];
}

const key = (s: { name: string; platform: string }) => `${s.name}@${s.platform}`;
const groupKey = (g: { name: string; scope: string }) => `${g.name}#${g.scope}`;

function groupInstalls(list: InstalledSkill[]): Group[] {
  const groups = new Map<string, Group>();
  for (const s of list) {
    const k = groupKey(s);
    const g = groups.get(k) ?? { name: s.name, scope: s.scope, version: s.version, author: s.author, tags: s.tags, registry: s.registry, installs: [] };
    g.installs.push(s);
    // Show the newest version among the installs; the outdated pill covers the rest.
    if (s.version > g.version) g.version = s.version;
    groups.set(k, g);
  }
  return Array.from(groups.values()).sort((a, b) => a.name.localeCompare(b.name));
}

export function Installed({ settings, onOpen, onCount, onOutdated, tagFilter, setTagFilter }: Props) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [updates, setUpdates] = useState<Record<string, UpdateResult>>({});
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showIssues, setShowIssues] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.installed(settings);
      setSkills(list);
      onCount(groupInstalls(list).length);
      const checks = list.length ? await api.checkUpdates(settings) : [];
      setUpdates(Object.fromEntries(checks.map((u) => [key(u), u])));
      onOutdated(checks.filter((u) => u.status === "outdated").length);
      setSelected((sel) => new Set([...sel].filter((k) => list.some((s) => groupKey(s) === k))));
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [settings, onCount, onOutdated]);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { listPlatforms(settings).then(setPlatforms).catch(() => setPlatforms([])); }, [settings]);

  const groups = useMemo(() => groupInstalls(skills), [skills]);
  const tags = useMemo(() => Array.from(new Set(skills.flatMap((s) => s.tags))).sort(), [skills]);
  const visible = tagFilter ? groups.filter((g) => g.tags.includes(tagFilter)) : groups;
  const outdated = Object.values(updates).filter((u) => u.status === "outdated");
  const issues = useMemo(() => [
    ...skills.filter((s) => s.present === false).map((s) => ({ key: key(s), skill: s, text: `${s.name} (${platformLabel(s.platform)}): files are missing from ${s.enabled ? s.path : s.parked_path}` })),
    ...Object.values(updates).filter((u) => u.status.startsWith("error")).map((u) => ({ key: key(u), skill: skills.find((s) => key(s) === key(u))!, text: `${u.name} (${platformLabel(u.platform)}): ${u.status.replace(/^error:\s*/, "")}` })),
  ], [skills, updates]);

  const run = async (label: string, ids: string[], fn: () => Promise<unknown>) => {
    setBusy(ids.join("|"));
    try {
      await fn();
      toast.success(label);
      await refresh();
    } catch (e) {
      toast.error(`${label} failed`, { description: String(e) });
    } finally {
      setBusy(null);
    }
  };

  const toggle = (s: InstalledSkill) =>
    run(`${s.enabled ? "Disabled" : "Enabled"} ${s.name} for ${platformLabel(s.platform)}`, [key(s)], () => (s.enabled ? api.disable : api.enable)(settings, s.name, s.platform));
  const uninstall = (s: InstalledSkill) => {
    if (confirm(`Remove ${s.name} from ${platformLabel(s.platform)}?\n\nIt goes to Removed for 30 days.`)) run(`Removed ${s.name} from ${platformLabel(s.platform)}`, [key(s)], () => api.uninstall(settings, s.name, s.platform));
  };
  const addTool = (g: Group, platform: string) =>
    run(`Installed ${g.name} for ${platformLabel(platform)}`, [groupKey(g)], () => api.installFor(settings, g.name, platform, g.registry, g.scope));
  const update = (s: InstalledSkill) => run(`Updated ${s.name} for ${platformLabel(s.platform)}`, [key(s)], () => api.update(settings, s.name, s.platform));
  const forget = (s: InstalledSkill) => run(`Forgot ${s.name} for ${platformLabel(s.platform)}`, [key(s)], () => api.uninstall(settings, s.name, s.platform));

  // Bulk actions act on every install of every selected group, sequentially so
  // the ledger writes never race.
  const selectedInstalls = groups.filter((g) => selected.has(groupKey(g))).flatMap((g) => g.installs);
  const bulk = async (label: string, fn: (s: InstalledSkill) => Promise<unknown>, filter: (s: InstalledSkill) => boolean = () => true) => {
    const targets = selectedInstalls.filter(filter);
    if (targets.length === 0) return;
    setBusy("*");
    let ok = 0;
    try {
      for (const s of targets) {
        try { await fn(s); ok++; } catch (e) { toast.error(`${label} ${s.name} (${platformLabel(s.platform)}) failed`, { description: String(e) }); }
      }
      toast.success(`${label} ${ok} of ${targets.length}`);
      setSelected(new Set());
      await refresh();
    } finally {
      setBusy(null);
    }
  };

  const toggleSelect = (g: Group) => setSelected((sel) => { const next = new Set(sel); const k = groupKey(g); if (next.has(k)) next.delete(k); else next.add(k); return next; });
  const allSelected = visible.length > 0 && visible.every((g) => selected.has(groupKey(g)));

  return (
    <>
      <PageHeader title="Installed" count={groups.length}>
        {tags.length > 0 && (
          <Select value={tagFilter ?? ""} onChange={(e) => setTagFilter(e.target.value || null)}>
            <option value="">All tags</option>
            {tags.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        )}
        {outdated.length > 0 && (
          <Button variant="primary" loading={busy === "*"} onClick={() => run(`Updated ${outdated.length} skill${outdated.length === 1 ? "" : "s"}`, ["*"], () => api.updateAll(settings))}>
            <ArrowUpCircle size={14} /> Update all ({outdated.length})
          </Button>
        )}
        <Button variant="ghost" onClick={refresh} disabled={loading} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></Button>
      </PageHeader>

      {issues.length > 0 && (
        <div className="mx-6 mt-4 rounded-lg border border-err/30 bg-err-bg/60 px-4 py-2.5 text-[12px] text-err">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} />
            <span className="flex-1">{issues.length} install{issues.length === 1 ? " has" : "s have"} a problem</span>
            <button className="underline" onClick={() => setShowIssues((v) => !v)}>{showIssues ? "Hide" : "View issues"}</button>
          </div>
          {showIssues && (
            <ul className="mt-2 space-y-1.5 border-t border-err/20 pt-2">
              {issues.map((i) => (
                <li key={i.key} className="flex items-center gap-2">
                  <span className="flex-1">{i.text}</span>
                  {i.skill.present === false && (
                    <>
                      <Button size="sm" onClick={() => run(`Reinstalled ${i.skill.name}`, [i.key], () => api.installFor(settings, i.skill.name, i.skill.platform, i.skill.registry, i.skill.scope))}>Reinstall</Button>
                      <Button size="sm" variant="ghost" onClick={() => forget(i.skill)}>Forget</Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="px-6 py-5 pb-24">
        {skills.length === 0 && !loading ? (
          <Empty icon={<Boxes size={36} strokeWidth={1.25} />} title="Nothing installed yet" hint="Open the Library, pick a skill, and click Install. It shows up here and in your AI tool." />
        ) : visible.length === 0 ? (
          <Empty icon={<Boxes size={36} strokeWidth={1.25} />} title={`No installed skills tagged “${tagFilter}”`} action={<Button onClick={() => setTagFilter(null)}>Clear filter</Button>} />
        ) : (
          <ul className="overflow-hidden rounded-lg border border-line bg-surface">
            {visible.map((g) => {
              const gk = groupKey(g);
              const isSelected = selected.has(gk);
              const groupBusy = busy === "*" || busy === gk || g.installs.some((s) => busy === key(s));
              const installedOn = new Set(g.installs.map((s) => s.platform));
              const available = platforms.filter((p) => !installedOn.has(p.name));
              const gUpdates = g.installs.map((s) => updates[key(s)]).filter((u) => u?.status === "outdated");
              const primary = g.installs.find((s) => s.enabled) ?? g.installs[0];
              return (
                <li key={gk} className={clsx("flex items-start gap-3 border-b border-line px-4 py-3 last:border-b-0", isSelected ? "bg-accent/5" : "hover:bg-surface-2/50")}>
                  <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(g)} aria-label={`Select ${g.name}`} className="mt-1.5 h-4 w-4 accent-accent" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <button className="font-medium hover:underline" onClick={() => onOpen({ name: g.name, version: g.version, author: g.author, tags: g.tags, dir: primary.enabled ? primary.path : primary.parked_path ?? primary.path, pills: [{ tone: "neutral", text: g.scope }] })}>{g.name}</button>
                      <span className="font-mono text-[12px] text-ink-3">{g.version}</span>
                      {g.scope === "project" && <Pill>project</Pill>}
                      {gUpdates.length > 0 && <Pill tone="warn">{gUpdates[0].available} available</Pill>}
                      <span className="ml-auto"><TagChips tags={g.tags} onPick={setTagFilter} /></span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {g.installs.map((s) => {
                        const u = updates[key(s)];
                        return (
                          <span key={s.path} className={clsx("group/chip inline-flex items-center gap-1 rounded-full border pl-1 pr-1 text-[12px]", s.enabled ? "border-line bg-surface" : "border-dashed border-line bg-surface-2 text-ink-3", s.present === false && "border-err/40")}>
                            <button
                              onClick={() => toggle(s)} disabled={groupBusy}
                              title={s.enabled ? "On — click to turn off" : "Off — click to turn on"}
                              className="inline-flex items-center gap-1.5 rounded-full px-1.5 py-0.5 hover:bg-surface-2"
                            >
                              <span className={clsx("h-2 w-2 rounded-full", s.enabled ? "bg-ok" : "bg-ink-3/50")} />
                              {platformLabel(s.platform)}
                            </button>
                            {u?.status === "outdated" && (
                              <button onClick={() => update(s)} disabled={groupBusy} title={`Update to ${u.available}`} className="rounded-full p-0.5 text-warn hover:bg-warn-bg"><ArrowUpCircle size={13} /></button>
                            )}
                            <button onClick={() => uninstall(s)} disabled={groupBusy} title={`Remove from ${platformLabel(s.platform)}`} className="rounded-full p-0.5 text-ink-3 opacity-0 transition-opacity hover:bg-err-bg hover:text-err group-hover/chip:opacity-100 focus:opacity-100"><X size={12} /></button>
                          </span>
                        );
                      })}
                      {available.length > 0 && (
                        <label className="inline-flex items-center gap-1 rounded-full border border-dashed border-line px-2 py-0.5 text-[12px] text-ink-2 hover:text-ink">
                          <Plus size={12} />
                          <select
                            value="" disabled={groupBusy}
                            onChange={(e) => { if (e.target.value) addTool(g, e.target.value); }}
                            className="bg-transparent text-[12px] outline-none"
                            aria-label={`Install ${g.name} for another tool`}
                          >
                            <option value="">Add tool</option>
                            {available.filter((p) => p.detected).map((p) => <option key={p.name} value={p.name}>{platformLabel(p.name)}</option>)}
                            {available.some((p) => !p.detected) && <option disabled>──</option>}
                            {available.filter((p) => !p.detected).map((p) => <option key={p.name} value={p.name}>{platformLabel(p.name)}</option>)}
                          </select>
                        </label>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {selected.size > 0 && (
        <div className="fixed bottom-4 left-1/2 z-10 flex w-[min(720px,calc(100vw-14rem-2rem))] -translate-x-1/2 items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 shadow-xl" style={{ marginLeft: "6.5rem" }}>
          <span className="mr-auto font-medium">{selected.size} selected</span>
          <Button size="sm" variant="ghost" onClick={() => setSelected(allSelected ? new Set() : new Set(visible.map(groupKey)))}>{allSelected ? "Clear" : "Select all"}</Button>
          <Button size="sm" disabled={busy !== null} onClick={() => bulk("Enabled", (s) => api.enable(settings, s.name, s.platform), (s) => !s.enabled)}>Enable</Button>
          <Button size="sm" disabled={busy !== null} onClick={() => bulk("Disabled", (s) => api.disable(settings, s.name, s.platform), (s) => s.enabled)}>Disable</Button>
          <Button size="sm" disabled={busy !== null || !selectedInstalls.some((s) => updates[key(s)]?.status === "outdated")} onClick={() => bulk("Updated", (s) => api.update(settings, s.name, s.platform), (s) => updates[key(s)]?.status === "outdated")}><ArrowUpCircle size={13} /> Update</Button>
          <Button size="sm" variant="danger" disabled={busy !== null} onClick={() => { if (confirm(`Remove ${selectedInstalls.length} install${selectedInstalls.length === 1 ? "" : "s"}?\n\nThey go to Removed for 30 days.`)) bulk("Removed", (s) => api.uninstall(settings, s.name, s.platform)); }}><Trash2 size={13} /> Remove</Button>
        </div>
      )}
    </>
  );
}
