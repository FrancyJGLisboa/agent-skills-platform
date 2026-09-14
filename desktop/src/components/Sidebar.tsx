import { clsx } from "clsx";
import { Boxes, Library, Settings, Trash2 } from "lucide-react";
import type { Tab } from "../App";

interface Props {
  tab: Tab;
  setTab: (tab: Tab) => void;
  counts: Partial<Record<Tab, number>>;
  ready: boolean;
}

const ITEMS: { id: Tab; label: string; icon: typeof Boxes }[] = [
  { id: "installed", label: "Installed", icon: Boxes },
  { id: "registry", label: "Registry", icon: Library },
  { id: "trash", label: "Recycle bin", icon: Trash2 },
];

export function Sidebar({ tab, setTab, counts, ready }: Props) {
  const item = (id: Tab, label: string, Icon: typeof Boxes) => {
    const active = tab === id;
    const disabled = !ready && id !== "settings";
    return (
      <button
        key={id}
        disabled={disabled}
        onClick={() => setTab(id)}
        className={clsx(
          "flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] transition-colors",
          active ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:bg-surface-2/60 hover:text-ink",
          disabled && "opacity-40 pointer-events-none",
        )}
      >
        <Icon size={16} strokeWidth={1.75} className={active ? "text-accent" : ""} />
        <span className="flex-1">{label}</span>
        {counts[id] !== undefined && counts[id]! > 0 && <span className="text-[11px] text-ink-3">{counts[id]}</span>}
      </button>
    );
  };

  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-line bg-surface px-3 pb-3 pt-4">
      <div className="mb-4 flex items-center gap-2 px-2.5">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[12px] font-bold text-accent-ink">A</span>
        <span className="text-[13px] font-semibold">Agent Skills</span>
      </div>
      <nav className="flex flex-col gap-0.5">{ITEMS.map((i) => item(i.id, i.label, i.icon))}</nav>
      <div className="mt-auto">{item("settings", "Settings", Settings)}</div>
    </aside>
  );
}
