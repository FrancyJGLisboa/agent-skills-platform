import { useCallback, useEffect, useState } from "react";
import { Toaster } from "sonner";
import { isConfigured, library, loadSettings, saveSettings, Settings } from "./lib/cli";
import { toast } from "sonner";
import { checkForUpdates } from "./lib/updates";
import { Sidebar } from "./components/Sidebar";
import { Installed } from "./components/Installed";
import { Registry } from "./components/Registry";
import { Trash } from "./components/Trash";
import { SettingsView } from "./components/SettingsView";
import { DrawerSkill, SkillDrawer } from "./components/SkillDrawer";

export type Tab = "installed" | "registry" | "trash" | "settings";

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(() => loadSettings());
  const [tab, setTab] = useState<Tab>(() => (isConfigured(loadSettings()) ? "installed" : "settings"));
  const [counts, setCounts] = useState<Partial<Record<Tab, number>>>({});
  const [outdated, setOutdated] = useState(0);
  const [drawer, setDrawer] = useState<DrawerSkill | null>(null);
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  // Bumping this remounts the data screens so an install on one shows on another.
  const [epoch, setEpoch] = useState(0);
  const bump = useCallback(() => setEpoch((n) => n + 1), []);
  const count = (id: Tab) => (n: number) => setCounts((c) => (c[id] === n ? c : { ...c, [id]: n }));
  const closeDrawer = useCallback(() => setDrawer(null), []);

  // One silent update check per launch; a toast offers the install.
  useEffect(() => { checkForUpdates({ silent: true }); }, []);

  // Keep the team library current: one background sync per launch. Failures
  // are non-fatal; the last synced copy still works offline.
  useEffect(() => {
    if (!settings?.libraryUrl) return;
    library.sync(settings.libraryUrl)
      .then((info) => { if (info.path !== settings.registry) { const next = { ...settings, registry: info.path }; saveSettings(next); setSettings(next); } bump(); })
      .catch((e) => toast.warning("Library not updated", { description: String(e) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-full">
      <Sidebar tab={tab} setTab={setTab} counts={counts} outdated={outdated} ready={isConfigured(settings)} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        {tab === "settings" || !isConfigured(settings) ? (
          <SettingsView
            initial={settings}
            onSave={(s) => { saveSettings(s); setSettings(s); bump(); setTab("installed"); }}
          />
        ) : tab === "installed" ? (
          <Installed key={epoch} settings={settings} onOpen={setDrawer} onCount={count("installed")} onOutdated={setOutdated} tagFilter={tagFilter} setTagFilter={setTagFilter} />
        ) : tab === "registry" ? (
          <Registry key={epoch} settings={settings} onOpen={setDrawer} onInstalled={bump} onCount={count("registry")} tagFilter={tagFilter} setTagFilter={setTagFilter} goToSettings={() => setTab("settings")} />
        ) : (
          <Trash key={epoch} settings={settings} onRestored={bump} onCount={count("trash")} />
        )}
      </main>
      <SkillDrawer skill={drawer} onClose={closeDrawer} onTag={setTagFilter} />
      <Toaster position="bottom-right" richColors closeButton toastOptions={{ style: { fontSize: 13 } }} />
    </div>
  );
}
