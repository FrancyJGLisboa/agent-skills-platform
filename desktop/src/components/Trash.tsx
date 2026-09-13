import { useCallback, useEffect, useState } from "react";
import { api, Settings, TrashItem } from "../lib/cli";

interface Props {
  settings: Settings;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onRestored: () => void;
}

const TTL_DAYS = 30;

export function Trash({ settings, onError, onNotice, onRestored }: Props) {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setItems(await api.trash(settings));
    } catch (e) {
      onError(String(e));
    }
  }, [settings, onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const restore = async (item: TrashItem, force = false) => {
    setBusy(item.item);
    try {
      await api.restore(settings, item.name, force);
      onNotice(`Restored ${item.name} to ${item.origin}`);
      onRestored();
      await refresh();
    } catch (e) {
      const message = String(e);
      if (!force && message.includes("already exists") && confirm(`${item.origin} already exists. Replace it?`)) {
        await restore(item, true);
        return;
      }
      onError(message);
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
      onNotice(`Purged ${purged.length} item${purged.length === 1 ? "" : "s"}`);
      await refresh();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(null);
    }
  };

  const age = (iso: string) => Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);

  return (
    <section>
      <header className="toolbar">
        <h2>Recycle bin <span className="count">{items.length}</span></h2>
        <button disabled={busy !== null || items.length === 0} onClick={() => purge(TTL_DAYS)}>
          Purge older than {TTL_DAYS} days
        </button>
        <button className="danger" disabled={busy !== null || items.length === 0} onClick={() => purge(0)}>
          Empty bin
        </button>
        <button onClick={refresh}>Refresh</button>
      </header>

      {items.length === 0 ? (
        <p className="muted">Recycle bin is empty. Uninstalled and removed skills land here for {TTL_DAYS} days.</p>
      ) : (
        <ul className="cards">
          {items.map((item) => {
            const days = age(item.trashed_at);
            return (
              <li key={item.item} className="card">
                <div className="card-head">
                  <strong>{item.name}</strong>
                  <span className="pill">{item.kind === "install" ? "uninstalled" : "removed from registry"}</span>
                  <span className={`muted ${days >= TTL_DAYS ? "err-text" : ""}`}>
                    {days === 0 ? "today" : `${days} day${days === 1 ? "" : "s"} ago`}
                  </span>
                </div>
                <code className="path" title={item.origin}><span>{item.origin}</span></code>
                <div className="actions">
                  <button className="primary" disabled={busy !== null} onClick={() => restore(item)}>
                    {busy === item.item ? "Restoring…" : "Restore"}
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
