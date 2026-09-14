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

/// Run `skill_registry.py <args> --json` in `cwd` and return its output.
///
/// `cwd` matters: project-scope installs resolve against the working
/// directory, exactly as they do for a user running the CLI.
#[tauri::command]
fn registry(
    python: String,
    scripts_dir: String,
    cwd: Option<String>,
    args: Vec<String>,
) -> Result<CliResult, String> {
    let script = registry_script(&scripts_dir)?;
    let mut command = Command::new(&python);
    command.arg(&script).args(&args).arg("--json");
    if let Some(dir) = cwd.filter(|d| !d.is_empty()) {
        command.current_dir(dir);
    }
    let output = command
        .output()
        .map_err(|e| format!("could not run {python}: {e}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let data = serde_json::from_str(&stdout).unwrap_or(serde_json::Value::Null);
    Ok(CliResult {
        code: output.status.code().unwrap_or(-1),
        data,
        stdout,
        stderr,
    })
}

/// Supported install platforms, read from `scripts/platforms.py` so the UI
/// never drifts from the CLI's table.
#[tauri::command]
fn platforms(python: String, scripts_dir: String) -> Result<Vec<String>, String> {
    let code = "import json, sys; sys.path.insert(0, sys.argv[1]); \
                import platforms; print(json.dumps(platforms.list_supported_platforms()))";
    let output = Command::new(&python)
        .args(["-c", code, &scripts_dir])
        .output()
        .map_err(|e| format!("could not run {python}: {e}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            registry,
            platforms,
            default_scripts_dir,
            skill_files,
            skill_file
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
