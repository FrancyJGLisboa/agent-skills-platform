import { useCallback, useEffect, useState } from "react";
import { loadSettings, saveSettings, Settings } from "./lib/cli";
import { Installed } from "./components/Installed";
import { Registry } from "./components/Registry";
import { Trash } from "./components/Trash";
import { SettingsView } from "./components/SettingsView";
import "./App.css";

type Tab = "installed" | "registry" | "trash" | "settings";

interface Toast {
  kind: "error" | "notice";
  message: string;
}

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(() => loadSettings());
  const [tab, setTab] = useState<Tab>(() => (loadSettings() ? "installed" : "settings"));
  const [toast, setToast] = useState<Toast | null>(null);
  // Bumping this remounts the data tabs so an install on one tab shows on another.
  const [epoch, setEpoch] = useState(0);

  const onError = useCallback((message: string) => setToast({ kind: "error", message }), []);
  const onNotice = useCallback((message: string) => setToast({ kind: "notice", message }), []);
  const bump = useCallback(() => setEpoch((n) => n + 1), []);

  useEffect(() => {
    if (!toast || toast.kind === "error") return;
    const id = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(id);
  }, [toast]);

  const tabs: [Tab, string][] = [
    ["installed", "Installed"],
    ["registry", "Registry"],
    ["trash", "Recycle bin"],
    ["settings", "Settings"],
  ];

  return (
    <div className="app">
      <nav className="tabs">
        <span className="brand">Agent Skills</span>
        {tabs.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)} disabled={!settings && id !== "settings"}>
            {label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "settings" || !settings ? (
          <SettingsView
            initial={settings}
            onError={onError}
            onSave={(s) => {
              saveSettings(s);
              setSettings(s);
              bump();
              setTab("installed");
              onNotice("Settings saved");
            }}
          />
        ) : tab === "installed" ? (
          <Installed key={epoch} settings={settings} onError={onError} onNotice={onNotice} />
        ) : tab === "registry" ? (
          <Registry key={epoch} settings={settings} onError={onError} onNotice={onNotice} onInstalled={bump} />
        ) : (
          <Trash key={epoch} settings={settings} onError={onError} onNotice={onNotice} onRestored={bump} />
        )}
      </main>

      {toast && (
        <div className={`toast ${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
          <pre>{toast.message}</pre>
          <button onClick={() => setToast(null)} aria-label="Dismiss">×</button>
        </div>
      )}
    </div>
  );
}
