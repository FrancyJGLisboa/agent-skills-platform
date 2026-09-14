// In-app updates: check GitHub Releases' latest.json (signed with the key in
// tauri.conf.json), download, install, relaunch. Non-fatal when offline or in dev.
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { toast } from "sonner";

export async function checkForUpdates(opts: { silent: boolean }): Promise<void> {
  let update;
  try {
    update = await check();
  } catch (e) {
    if (!opts.silent) toast.error("Could not check for updates", { description: String(e) });
    return;
  }
  if (!update) {
    if (!opts.silent) toast.success("You're on the latest version");
    return;
  }
  toast(`Version ${update.version} is available`, {
    description: update.body?.split("\n")[0],
    duration: 15000,
    action: {
      label: "Install and restart",
      onClick: async () => {
        const id = toast.loading("Downloading update…");
        try {
          await update.downloadAndInstall();
          toast.dismiss(id);
          await relaunch();
        } catch (e) {
          toast.error("Update failed", { id, description: String(e) });
        }
      },
    },
  });
}
