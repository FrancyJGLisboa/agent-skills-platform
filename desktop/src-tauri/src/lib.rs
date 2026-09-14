//! Thin bridge from the desktop UI to `scripts/skill_registry.py`.
//!
//! The Python CLI stays the single source of truth for registry and
//! installed-skill logic; every command here runs it with `--json` and hands
//! the parsed output to the UI. No registry logic lives in Rust. The two file
//! commands only read inside a skill directory the UI already knows about, so
//! the detail view can show `SKILL.md` and the file tree.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri_plugin_shell::ShellExt;

mod library;

#[derive(Serialize)]
pub struct CliResult {
    /// Process exit code (`update --check` uses 2 for "outdated").
    pub code: i32,
    /// Parsed stdout when it was JSON, otherwise null.
    pub data: serde_json::Value,
    /// Raw stdout when it was not JSON.
    pub stdout: String,
    pub stderr: String,
}

fn registry_script(scripts_dir: &str) -> Result<PathBuf, String> {
    let script = Path::new(scripts_dir).join("skill_registry.py");
    if script.is_file() {
        Ok(script)
    } else {
        Err(format!("skill_registry.py not found in {scripts_dir}"))
    }
}

fn cli_result(code: Option<i32>, stdout: &[u8], stderr: &[u8]) -> CliResult {
    let stdout = String::from_utf8_lossy(stdout).to_string();
    CliResult {
        code: code.unwrap_or(-1),
        data: serde_json::from_str(&stdout).unwrap_or(serde_json::Value::Null),
        stdout,
        stderr: String::from_utf8_lossy(stderr).to_string(),
    }
}

/// Run `skill_registry <args> --json` and return its output.
///
/// With `scripts_dir` set (the advanced "use a checkout" mode) this runs
/// `python skill_registry.py`; otherwise it runs the bundled sidecar, so an
/// installed app needs neither Python nor a checkout. `cwd` matters either
/// way: project-scope installs resolve against the working directory, exactly
/// as they do for a user running the CLI.
#[tauri::command]
async fn registry(
    app: tauri::AppHandle,
    python: Option<String>,
    scripts_dir: Option<String>,
    cwd: Option<String>,
    args: Vec<String>,
) -> Result<CliResult, String> {
    let cwd = cwd.filter(|d| !d.is_empty());
    if let Some(dir) = scripts_dir.filter(|d| !d.is_empty()) {
        let script = registry_script(&dir)?;
        let python = python.filter(|p| !p.is_empty()).unwrap_or_else(|| "python3".into());
        let mut command = Command::new(&python);
        command.arg(&script).args(&args).arg("--json");
        if let Some(dir) = cwd {
            command.current_dir(dir);
        }
        let output = command
            .output()
            .map_err(|e| format!("could not run {python}: {e}"))?;
        return Ok(cli_result(output.status.code(), &output.stdout, &output.stderr));
    }

    let mut command = app
        .shell()
        .sidecar("skill_registry")
        .map_err(|e| format!("bundled skill_registry is missing: {e}"))?
        .args(&args)
        .arg("--json");
    if let Some(dir) = cwd {
        command = command.current_dir(dir);
    }
    let output = command
        .output()
        .await
        .map_err(|e| format!("could not run bundled skill_registry: {e}"))?;
    Ok(cli_result(output.status.code(), &output.stdout, &output.stderr))
}

/// Supported install platforms, from `skill_registry platforms --json`, so the
/// UI never drifts from the CLI's table.
#[tauri::command]
async fn platforms(
    app: tauri::AppHandle,
    python: Option<String>,
    scripts_dir: Option<String>,
) -> Result<serde_json::Value, String> {
    let result = registry(app, python, scripts_dir, None, vec!["platforms".into()]).await?;
    if result.code != 0 || result.data.is_null() {
        return Err(if result.stderr.trim().is_empty() { result.stdout } else { result.stderr });
    }
    Ok(result.data)
}

/// Best guess for where the platform's `scripts/` directory lives.
///
/// Order: `$AGENT_SKILLS_PLATFORM/scripts`, the repo this app was built from
/// (dev builds), then the documented global install paths.
#[tauri::command]
fn default_scripts_dir() -> String {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(root) = std::env::var("AGENT_SKILLS_PLATFORM") {
        candidates.push(Path::new(&root).join("scripts"));
    }
    candidates.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../scripts"));
    if let Some(home) = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")) {
        for rel in [
            ".claude/skills/agent-skills-platform/scripts",
            ".agents/skills/agent-skills-platform/scripts",
            ".copilot/skills/agent-skills-platform/scripts",
        ] {
            candidates.push(Path::new(&home).join(rel));
        }
    }
    candidates
        .into_iter()
        .find(|p| p.join("skill_registry.py").is_file())
        .and_then(|p| p.canonicalize().ok())
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default()
}

const SKIPPED_DIRS: [&str; 6] = [".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"];
const MAX_TREE_ENTRIES: usize = 500;

#[derive(Serialize)]
pub struct FileEntry {
    /// Path relative to the skill directory, `/`-separated.
    pub path: String,
    pub size: u64,
}

fn walk(root: &Path, dir: &Path, out: &mut Vec<FileEntry>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    let mut entries: Vec<_> = entries.flatten().collect();
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        if out.len() >= MAX_TREE_ENTRIES {
            return;
        }
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_dir() {
            if !SKIPPED_DIRS.contains(&name.as_str()) {
                walk(root, &path, out);
            }
        } else if let Ok(rel) = path.strip_prefix(root) {
            out.push(FileEntry {
                path: rel.to_string_lossy().replace('\\', "/"),
                size: entry.metadata().map(|m| m.len()).unwrap_or(0),
            });
        }
    }
}

/// Files under a skill directory, for the detail view's tree.
#[tauri::command]
fn skill_files(dir: String) -> Result<Vec<FileEntry>, String> {
    let root = Path::new(&dir);
    if !root.is_dir() {
        return Err(format!("not a directory: {dir}"));
    }
    let mut out = Vec::new();
    walk(root, root, &mut out);
    Ok(out)
}

const MAX_FILE_BYTES: u64 = 512 * 1024;

/// Read one text file inside a skill directory. Refuses paths that escape
/// `dir` and files larger than 512 KiB.
#[tauri::command]
fn skill_file(dir: String, file: String) -> Result<String, String> {
    let root = Path::new(&dir).canonicalize().map_err(|e| e.to_string())?;
    let target = root.join(&file).canonicalize().map_err(|e| e.to_string())?;
    if !target.starts_with(&root) {
        return Err(format!("{file} is outside the skill directory"));
    }
    let size = std::fs::metadata(&target).map_err(|e| e.to_string())?.len();
    if size > MAX_FILE_BYTES {
        return Err(format!("{file} is {size} bytes; the viewer stops at {MAX_FILE_BYTES}"));
    }
    let bytes = std::fs::read(&target).map_err(|e| e.to_string())?;
    String::from_utf8(bytes).map_err(|_| format!("{file} is not UTF-8 text"))
}

/// Clone or update the team library at `url`; returns where it landed.
#[tauri::command]
async fn library_sync(url: String) -> Result<library::LibraryInfo, String> {
    tauri::async_runtime::spawn_blocking(move || library::sync(&url))
        .await
        .map_err(|e| e.to_string())?
}

/// Local state of the library without a network round-trip.
#[tauri::command]
fn library_status(url: String) -> Result<Option<library::LibraryInfo>, String> {
    library::status(&url)
}

#[tauri::command]
fn library_has_registry(path: String) -> bool {
    library::has_registry(&path)
}

/// Store (or, with an empty token, remove) the access token for a library's host.
#[tauri::command]
fn library_set_token(url: String, token: String) -> Result<(), String> {
    library::set_token(&url, &token)
}

#[tauri::command]
fn library_has_token(url: String) -> bool {
    library::has_token(&url)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            registry,
            platforms,
            default_scripts_dir,
            skill_files,
            skill_file,
            library_sync,
            library_status,
            library_has_registry,
            library_set_token,
            library_has_token
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
