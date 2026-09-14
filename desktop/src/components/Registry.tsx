import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, Library, RefreshCw, Search } from "lucide-react";
import { api, library, RegistrySkill, Settings, StaleResult } from "../lib/cli";
import { Button, Empty, Input, PageHeader, Pill, Select, TagChips } from "./ui";
import { DrawerSkill } from "./SkillDrawer";

interface Props {
  settings: Settings;
  onOpen: (skill: DrawerSkill) => void;
  onInstalled: () => void;
  onCount: (n: number) => void;
  tagFilter: string | null;
  setTagFilter: (t: string | null) => void;
  goToSettings: () => void;
}

type Scope = "user" | "project";

export function Registry({ settings, onOpen, onInstalled, onCount, tagFilter, setTagFilter, goToSettings }: Props) {
  const [skills, setSkills] = useState<RegistrySkill[]>([]);
  const [stale, setStale] = useState<Record<string, StaleResult>>({});
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>(settings.projectDir ? "project" : "user");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (sync = false) => {
    if (!settings.registry) { setLoading(false); return; }
    setLoading(true);
    try {
      if (sync && settings.libraryUrl) {
        const info = await library.sync(settings.libraryUrl);
        toast.success(`Library up to date`, { description: `${info.branch} @ ${info.commit}` });
      }
      const [list, staleness] = await Promise.all([api.registryList(settings), api.stale(settings)]);
      setSkills(list);
      onCount(list.length);
      setStale(Object.fromEntries(staleness.map((s) => [s.name, s])));
    } catch (e) {
      toast.error("Could not read the registry", { description: String(e) });
    } finally {
      setLoading(false);
    }
  }, [settings, onCount]);

  useEffect(() => { refresh(); }, [refresh]);

  const tags = useMemo(() => Array.from(new Set(skills.flatMap((s) => s.tags))).sort(), [skills]);
  const visible = skills.filter((s) => {
    if (tagFilter && !s.tags.includes(tagFilter)) return false;
    const q = query.trim().toLowerCase();
    return !q || [s.name, s.description, s.author, s.tags.join(" ")].join(" ").toLowerCase().includes(q);
  });

  const install = async (name: string, force = false) => {
    setBusy(name);
    try {
      await api.install(settings, name, scope, force);
      toast.success(`Installed ${name}`, { description: `${settings.platform} · ${scope}` });
      onInstalled();
    } catch (e) {
      const message = String(e);
      if (!force && message.includes("already installed") && confirm(`${name} is already installed there. Overwrite it?`)) {
        await install(name, true);
        return;
      }
      toast.error(`Install ${name} failed`, { description: message });
    } finally {
      setBusy(null);
    }
  };

  const installTag = async () => {
    if (!tagFilter) return;
    setBusy(`tag:${tagFilter}`);
    try {
      await api.installTag(settings, tagFilter, scope);
      toast.success(`Installed every “${tagFilter}” skill`, { description: `${settings.platform} · ${scope}` });
      onInstalled();
    } catch (e) {
      toast.error("Bulk install failed", { description: String(e) });
    } finally {
      setBusy(null);
    }
  };

  const pillsFor = (s: RegistrySkill): DrawerSkill["pills"] => {
    const out: NonNullable<DrawerSkill["pills"]> = [];
    if (s.validation) out.push({ tone: s.validation.valid ? "ok" : "err", text: s.validation.valid ? "valid" : `${s.validation.errors} errors` });
    if (s.security) out.push({ tone: s.security.clean ? "ok" : "err", text: s.security.clean ? "clean" : `${s.security.issues} issues` });
    const st = stale[s.name];
    if (st && st.status !== "fresh" && st.status !== "unknown") out.push({ tone: st.status === "overdue" ? "err" : "warn", text: `review ${st.status.replace("_", " ")}` });
    return out;
  };

  if (!settings.registry) {
    return (
      <>
        <PageHeader title="Library" />
        <Empty icon={<Library size={36} strokeWidth={1.25} />} title="No team library yet" hint="Paste the library link from your admin in Settings to browse and install skills." action={<Button variant="primary" onClick={goToSettings}>Open settings</Button>} />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Library" count={skills.length}>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3" />
          <Input placeholder="Search skills…" value={query} onChange={(e) => setQuery(e.target.value)} className="w-56 pl-8" />
        </div>
        {tags.length > 0 && (
          <Select value={tagFilter ?? ""} onChange={(e) => setTagFilter(e.target.value || null)}>
            <option value="">All tags</option>
            {tags.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        )}
        {settings.projectDir && (
          <Select value={scope} onChange={(e) => setScope(e.target.value as Scope)} title="Install scope">
            <option value="user">For me</option>
            <option value="project">This project</option>
          </Select>
        )}
        {tagFilter && (
          <Button variant="primary" loading={busy === `tag:${tagFilter}`} disabled={busy !== null} onClick={installTag}>
            <Download size={14} /> Install all “{tagFilter}” ({visible.length})
          </Button>
        )}
        <Button variant="ghost" onClick={() => refresh(true)} disabled={loading} aria-label="Refresh" title={settings.libraryUrl ? "Check the team library for updates" : "Reload"}><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></Button>
      </PageHeader>

      <div className="px-6 py-5">
        <p dir="rtl" className="mb-3 truncate text-left font-mono text-[11px] text-ink-3"><bdi>{settings.libraryUrl || settings.registry}</bdi></p>
        {skills.length === 0 && !loading ? (
          <Empty icon={<Library size={36} strokeWidth={1.25} />} title="The library is empty" hint="Nothing has been published to it yet." />
        ) : visible.length === 0 ? (
          <Empty icon={<Search size={36} strokeWidth={1.25} />} title="No skills match" action={<Button onClick={() => { setQuery(""); setTagFilter(null); }}>Clear filters</Button>} />
        ) : (
          <ul className="overflow-hidden rounded-lg border border-line bg-surface">
            {visible.map((s) => (
              <li
                key={`${s.author}/${s.name}/${s.version}`}
                onClick={() => onOpen({ name: s.name, version: s.version, description: s.description, author: s.author, tags: s.tags, dir: `${settings.registry}/${s.path}`, pills: pillsFor(s) })}
                className="group flex cursor-pointer items-start gap-4 border-b border-line px-4 py-3 last:border-b-0 hover:bg-surface-2/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{s.name}</span>
                    <span className="font-mono text-[12px] text-ink-3">{s.version}</span>
                    {s.author && <span className="text-[12px] text-ink-3">by {s.author}</span>}
                    {pillsFor(s)?.map((p) => <Pill key={p.text} tone={p.tone}>{p.text}</Pill>)}
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-ink-2">{s.description}</p>
                  <div className="mt-1.5"><TagChips tags={s.tags} onPick={setTagFilter} /></div>
                </div>
                <div className="shrink-0 pt-0.5" onClick={(e) => e.stopPropagation()}>
                  <Button size="sm" variant="primary" loading={busy === s.name} disabled={busy !== null} onClick={() => install(s.name)}>
                    <Download size={13} /> Install
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
