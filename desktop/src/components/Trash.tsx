import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { api, Settings, TrashItem } from "../lib/cli";
import { Button, Empty, PageHeader, PathText, Pill } from "./ui";

interface Props {
  settings: Settings;
  onRestored: () => void;
  onCount: (n: number) => void;
}

const TTL_DAYS = 30;
const age = (iso: string) => Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);

export function Trash({ settings, onRestored, onCount }: Props) {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.trash(settings);
      setItems(list);
      onCount(list.length);
    } catch (e) {
      toast.error(String(e));
    }
  }, [settings, onCount]);

  useEffect(() => { refresh(); }, [refresh]);

  const restore = async (item: TrashItem, force = false) => {
    setBusy(item.item);
    try {
      await api.restore(settings, item.name, force);
      toast.success(`Restored ${item.name}`, { description: item.origin });
      onRestored();
      await refresh();
    } catch (e) {
      const message = String(e);
      if (!force && message.includes("already exists") && confirm(`${item.origin} already exists. Replace it?`)) {
        await restore(item, true);
        return;
      }
      toast.error(`Restore ${item.name} failed`, { description: message });
    } finally {
      setBusy(null);
    }
  };

  const purge = async (olderThan: number) => {
    const what = olderThan === 0 ? "everything in the recycle bin" : `items older than ${olderThan} days`;
    if (!confirm(`Permanently delete ${what}?`)) return;
    setBusy("purge");
    try {
      const purged = await api.purge(settings, olderThan);
      toast.success(`Purged ${purged.length} item${purged.length === 1 ? "" : "s"}`);
      await refresh();
    } catch (e) {
      toast.error("Purge failed", { description: String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader title="Removed" count={items.length}>
        <Button disabled={busy !== null || items.length === 0} onClick={() => purge(TTL_DAYS)}>Purge older than {TTL_DAYS} days</Button>
        <Button variant="danger" disabled={busy !== null || items.length === 0} onClick={() => purge(0)}><Trash2 size={14} /> Delete all</Button>
        <Button variant="ghost" onClick={refresh} aria-label="Refresh"><RefreshCw size={14} /></Button>
      </PageHeader>

      <div className="px-6 py-5">
        {items.length === 0 ? (
          <Empty icon={<Trash2 size={36} strokeWidth={1.25} />} title="Nothing removed" hint={`Skills you uninstall stay here for ${TTL_DAYS} days in case you want them back.`} />
        ) : (
          <ul className="overflow-hidden rounded-lg border border-line bg-surface">
            {items.map((item) => {
              const days = age(item.trashed_at);
              return (
                <li key={item.item} className="flex items-center gap-4 border-b border-line px-4 py-3 last:border-b-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      <Pill>{item.kind === "install" ? "uninstalled" : "removed from registry"}</Pill>
                      <span className={days >= TTL_DAYS ? "text-[12px] text-err" : "text-[12px] text-ink-3"}>
                        {days === 0 ? "today" : `${days} day${days === 1 ? "" : "s"} ago`}
                      </span>
                    </div>
                    <PathText path={item.origin} className="mt-1" />
                  </div>
                  <Button size="sm" loading={busy === item.item} disabled={busy !== null} onClick={() => restore(item)}>
                    <RotateCcw size={13} /> Restore
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
