import { useCallback, useState } from "react";
import { Toaster } from "sonner";
import { loadSettings, saveSettings, Settings } from "./lib/cli";
import { Sidebar } from "./components/Sidebar";
import { Installed } from "./components/Installed";
import { Registry } from "./components/Registry";
import { Trash } from "./components/Trash";
import { SettingsView } from "./components/SettingsView";
import { DrawerSkill, SkillDrawer } from "./components/SkillDrawer";

export type Tab = "installed" | "registry" | "trash" | "settings";

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(() => loadSettings());
  const [tab, setTab] = useState<Tab>(() => (loadSettings() ? "installed" : "settings"));
  const [counts, setCounts] = useState<Partial<Record<Tab, number>>>({});
  const [drawer, setDrawer] = useState<DrawerSkill | null>(null);
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  // Bumping this remounts the data screens so an install on one shows on another.
  const [epoch, setEpoch] = useState(0);
  const bump = useCallback(() => setEpoch((n) => n + 1), []);
  const count = (id: Tab) => (n: number) => setCounts((c) => (c[id] === n ? c : { ...c, [id]: n }));
  const closeDrawer = useCallback(() => setDrawer(null), []);

  return (
    <div className="flex h-full">
      <Sidebar tab={tab} setTab={setTab} counts={counts} ready={settings !== null} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        {tab === "settings" || !settings ? (
          <SettingsView
            initial={settings}
            onSave={(s) => { saveSettings(s); setSettings(s); bump(); setTab("installed"); }}
          />
        ) : tab === "installed" ? (
          <Installed key={epoch} settings={settings} onOpen={setDrawer} onCount={count("installed")} tagFilter={tagFilter} setTagFilter={setTagFilter} />
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
