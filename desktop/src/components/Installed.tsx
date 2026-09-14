import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowUpCircle, Boxes, RefreshCw, Trash2 } from "lucide-react";
import { clsx } from "clsx";
import { api, InstalledSkill, Settings, UpdateResult } from "../lib/cli";
import { Button, Empty, PageHeader, PathText, Pill, Select, Switch, TagChips } from "./ui";
import { DrawerSkill } from "./SkillDrawer";

interface Props {
  settings: Settings;
  onOpen: (skill: DrawerSkill) => void;
  onCount: (n: number) => void;
  tagFilter: string | null;
  setTagFilter: (t: string | null) => void;
}

const key = (s: { name: string; platform: string }) => `${s.name}@${s.platform}`;

export function Installed({ settings, onOpen, onCount, tagFilter, setTagFilter }: Props) {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [updates, setUpdates] = useState<Record<string, UpdateResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.installed(settings);
      setSkills(list);
      onCount(list.length);
      const checks = list.length ? await api.checkUpdates(settings) : [];
      setUpdates(Object.fromEntries(checks.map((u) => [key(u), u])));
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [settings, onCount]);

  useEffect(() => { refresh(); }, [refresh]);

  const tags = useMemo(() => Array.from(new Set(skills.flatMap((s) => s.tags))).sort(), [skills]);
  const visible = tagFilter ? skills.filter((s) => s.tags.includes(tagFilter)) : skills;
  const outdated = Object.values(updates).filter((u) => u.status === "outdated");

  const act = async (skill: InstalledSkill, label: string, fn: () => Promise<unknown>) => {
    setBusy(key(skill));
    try {
      await fn();
      toast.success(`${label} ${skill.name}`, { description: skill.platform });
      await refresh();
    } catch (e) {
      toast.error(`${label} failed`, { description: String(e) });
    } finally {
      setBusy(null);
    }
  };

  const updateAll = async () => {
    setBusy("*");
    try {
      const results = await api.updateAll(settings);
      const n = results.filter((r) => r.status === "updated").length;
      toast.success(`Updated ${n} skill${n === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error("Update failed", { description: String(e) });
    } finally {
      setBusy(null);
      refresh();
    }
  };

  return (
    <>
      <PageHeader title="Installed" count={skills.length}>
        {tags.length > 0 && (
          <Select value={tagFilter ?? ""} onChange={(e) => setTagFilter(e.target.value || null)}>
            <option value="">All tags</option>
            {tags.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        )}
        {outdated.length > 0 && (
          <Button variant="primary" loading={busy === "*"} onClick={updateAll}>
            <ArrowUpCircle size={14} /> Update all ({outdated.length})
          </Button>
        )}
        <Button variant="ghost" onClick={refresh} disabled={loading} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></Button>
      </PageHeader>

      <div className="px-6 py-5">
        {skills.length === 0 && !loading ? (
          <Empty icon={<Boxes size={36} strokeWidth={1.25} />} title="Nothing installed yet" hint="Open the Library, pick a skill, and click Install. It shows up here and in your AI tool." />
        ) : visible.length === 0 ? (
          <Empty icon={<Boxes size={36} strokeWidth={1.25} />} title={`No installed skills tagged “${tagFilter}”`} action={<Button onClick={() => setTagFilter(null)}>Clear filter</Button>} />
        ) : (
          <ul className="overflow-hidden rounded-lg border border-line bg-surface">
            {visible.map((s) => {
              const u = updates[key(s)];
              const isBusy = busy === key(s) || busy === "*";
              return (
                <li
                  key={s.path}
                  onClick={() => onOpen({ name: s.name, version: s.version, author: s.author, tags: s.tags, dir: s.enabled ? s.path : s.parked_path ?? s.path,
                    pills: [{ tone: s.enabled ? "ok" : "neutral", text: s.enabled ? "enabled" : "disabled" }, { tone: "neutral", text: `${s.platform} · ${s.scope}` }] })}
                  className={clsx("group flex cursor-pointer items-center gap-4 border-b border-line px-4 py-3 last:border-b-0 hover:bg-surface-2/50", !s.enabled && "opacity-70")}
                >
                  <Switch checked={s.enabled} disabled={isBusy} label={s.enabled ? "Disable" : "Enable"}
                    onChange={() => act(s, s.enabled ? "Disabled" : "Enabled", () => (s.enabled ? api.disable : api.enable)(settings, s.name, s.platform))} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{s.name}</span>
                      <span className="font-mono text-[12px] text-ink-3">{s.version}</span>
                      <Pill>{s.platform}</Pill>
                      <Pill>{s.scope}</Pill>
                      {u?.status === "outdated" && <Pill tone="warn">{u.available} available</Pill>}
                      {u?.status.startsWith("error") && <Pill tone="err" title={u.status}>registry missing</Pill>}
                    </div>
                    <div className="mt-1 flex items-center gap-3">
                      <TagChips tags={s.tags} onPick={setTagFilter} />
                      <PathText path={s.path} className="min-w-0 flex-1" />
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100" onClick={(e) => e.stopPropagation()}>
                    <Button size="sm" disabled={isBusy || u?.status !== "outdated"} onClick={() => act(s, "Updated", () => api.update(settings, s.name, s.platform))}>
                      <ArrowUpCircle size={13} /> Update
                    </Button>
                    <Button size="sm" variant="danger" disabled={isBusy} onClick={() => {
                      if (confirm(`Uninstall ${s.name} from ${s.platform}?\n\nIt goes to the recycle bin for 30 days.`)) act(s, "Uninstalled", () => api.uninstall(settings, s.name, s.platform));
                    }}>
                      <Trash2 size={13} /> Uninstall
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
