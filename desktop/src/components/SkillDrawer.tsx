// Detail view for one skill: metadata, file tree, and rendered SKILL.md or any text file.
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronRight, File, FileText, X } from "lucide-react";
import { clsx } from "clsx";
import { FileEntry, skillFile, skillFiles } from "../lib/cli";
import { Pill, TagChips } from "./ui";

export interface DrawerSkill {
  name: string;
  version: string;
  description?: string;
  author?: string;
  tags: string[];
  /** Directory holding the skill's files (install path, parked path, or registry path). */
  dir: string;
  pills?: { tone: "ok" | "warn" | "err" | "neutral"; text: string }[];
}

interface Props {
  skill: DrawerSkill | null;
  onClose: () => void;
  onTag?: (tag: string) => void;
}

/** Drop a leading YAML frontmatter block; the drawer header already shows that metadata. */
const stripFrontmatter = (md: string) => md.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, "");

const formatSize = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

export function SkillDrawer({ skill, onClose, onTag }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [selected, setSelected] = useState("SKILL.md");
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!skill) return;
    setSelected("SKILL.md");
    setFiles([]);
    skillFiles(skill.dir).then(setFiles).catch((e) => setError(String(e)));
  }, [skill]);

  useEffect(() => {
    if (!skill) return;
    setContent(null);
    setError(null);
    skillFile(skill.dir, selected).then(setContent).catch((e) => setError(String(e)));
  }, [skill, selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tree = useMemo(() => {
    // Group by top-level directory so the tree reads like a file browser without nesting UI.
    const groups = new Map<string, FileEntry[]>();
    for (const f of files) {
      const slash = f.path.indexOf("/");
      const group = slash === -1 ? "" : f.path.slice(0, slash);
      groups.set(group, [...(groups.get(group) ?? []), f]);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
  }, [files]);

  if (!skill) return null;
  const isMarkdown = selected.toLowerCase().endsWith(".md");

  return (
    <div className="fixed inset-0 z-20 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <section
        role="dialog"
        aria-label={skill.name}
        onClick={(e) => e.stopPropagation()}
        className="relative flex h-full w-[min(880px,92vw)] flex-col border-l border-line bg-bg shadow-2xl"
      >
        <header className="flex items-start gap-3 border-b border-line bg-surface px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold">{skill.name}</h2>
              <span className="font-mono text-[12px] text-ink-3">{skill.version}</span>
              {skill.author && <span className="text-[12px] text-ink-3">by {skill.author}</span>}
              {skill.pills?.map((p) => <Pill key={p.text} tone={p.tone}>{p.text}</Pill>)}
            </div>
            {skill.description && <p className="mt-1 text-ink-2">{skill.description}</p>}
            {skill.tags.length > 0 && <div className="mt-2"><TagChips tags={skill.tags} max={12} onPick={(t) => { onTag?.(t); onClose(); }} /></div>}
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-md p-1 text-ink-3 hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </header>

        <div className="flex min-h-0 flex-1">
          <nav className="w-56 shrink-0 overflow-y-auto border-r border-line bg-surface py-2">
            {tree.map(([group, entries]) => (
              <div key={group || "."} className="mb-1">
                {group && (
                  <div className="flex items-center gap-1 px-3 py-1 text-[11px] font-medium uppercase tracking-wide text-ink-3">
                    <ChevronRight size={12} />{group}
                  </div>
                )}
                {entries.map((f) => {
                  const leaf = f.path.slice(group ? group.length + 1 : 0);
                  const active = f.path === selected;
                  return (
                    <button
                      key={f.path}
                      onClick={() => setSelected(f.path)}
                      title={`${f.path} · ${formatSize(f.size)}`}
                      className={clsx(
                        "flex w-full items-center gap-2 py-1 pr-3 text-left text-[12px]",
                        group ? "pl-7" : "pl-3",
                        active ? "bg-surface-2 text-ink" : "text-ink-2 hover:bg-surface-2/60 hover:text-ink",
                      )}
                    >
                      {leaf.toLowerCase().endsWith(".md") ? <FileText size={13} className="shrink-0" /> : <File size={13} className="shrink-0" />}
                      <span className="truncate">{leaf}</span>
                    </button>
                  );
                })}
              </div>
            ))}
            {files.length === 0 && !error && <p className="px-3 py-2 text-[12px] text-ink-3">Reading files…</p>}
          </nav>

          <div className="min-w-0 flex-1 overflow-y-auto px-6 py-5 selectable">
            <div className="mb-3 font-mono text-[11px] text-ink-3">{selected}</div>
            {error ? (
              <p className="text-err">{error}</p>
            ) : content === null ? (
              <p className="text-ink-3">Loading…</p>
            ) : isMarkdown ? (
              <div className="prose-skill"><ReactMarkdown remarkPlugins={[remarkGfm]}>{stripFrontmatter(content)}</ReactMarkdown></div>
            ) : (
              <pre className="overflow-auto rounded-lg border border-line bg-surface p-3 font-mono text-[12px] leading-5">{content}</pre>
            )}
          </div>
        </div>

        <footer className="border-t border-line bg-surface px-5 py-2">
          <span dir="rtl" className="block truncate text-left font-mono text-[11px] text-ink-3" title={skill.dir}><bdi>{skill.dir}</bdi></span>
        </footer>
      </section>
    </div>
  );
}
