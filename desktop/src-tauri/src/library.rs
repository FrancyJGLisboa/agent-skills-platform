//! Team library: a Git repository holding a `registry.json` skill registry,
//! cloned and kept current by the app so a non-technical user only ever
//! pastes a URL. libgit2 is vendored, so nothing here needs `git` installed.
//!
//! Private repositories authenticate with a personal access token kept in
//! the OS keychain (macOS Keychain, Windows Credential Manager, Secret
//! Service on Linux); the token never reaches the web view.

use git2::{build::RepoBuilder, Cred, CredentialType, FetchOptions, RemoteCallbacks, Repository};
use serde::Serialize;
use std::path::{Path, PathBuf};

const KEYRING_SERVICE: &str = "io.github.francyjglisboa.agent-skills";

#[derive(Serialize, Clone)]
pub struct LibraryInfo {
    pub url: String,
    pub name: String,
    /// Local clone; this is what `skill_registry --registry` receives.
    pub path: String,
    pub commit: String,
    pub branch: String,
    pub synced_at: String,
}

pub fn libraries_root() -> Result<PathBuf, String> {
    let home = std::env::var_os("AGENT_SKILLS_HOME")
        .map(PathBuf::from)
        .or_else(|| dirs::home_dir().map(|h| h.join(".agent-skills")))
        .ok_or("cannot determine home directory")?;
    Ok(home.join("libraries"))
}

/// `https://github.com/acme/skills.git` -> `github.com-acme-skills`.
pub fn slug(url: &str) -> Result<String, String> {
    let trimmed = url.trim().trim_end_matches('/').trim_end_matches(".git");
    if let Some(rest) = trimmed.strip_prefix("git@") {
        // scp-style ssh: git@host:org/repo
        let cleaned: String = rest.chars().map(|c| if c.is_alphanumeric() || c == '.' { c } else { '-' }).collect();
        return Ok(cleaned.trim_matches('-').to_string());
    }
    let parsed = url::Url::parse(trimmed).map_err(|e| format!("not a valid URL: {e}"))?;
    // file:// URLs (local libraries, tests) have no host.
    let host = match parsed.host_str() {
        Some(h) => h,
        None if parsed.scheme() == "file" => "local",
        None => return Err("URL has no host".into()),
    };
    let path = parsed.path().trim_matches('/');
    if path.is_empty() {
        return Err("URL has no repository path".into());
    }
    let cleaned: String = format!("{host}/{path}")
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '.' { c } else { '-' })
        .collect();
    Ok(cleaned.trim_matches('-').to_string())
}

fn display_name(url: &str) -> String {
    url.trim().trim_end_matches('/').trim_end_matches(".git").rsplit(['/', ':']).next().unwrap_or("library").to_string()
}

fn keyring_entry(url: &str) -> Result<keyring::Entry, String> {
    let host = url::Url::parse(url).ok().and_then(|u| u.host_str().map(str::to_string)).unwrap_or_else(|| slug(url).unwrap_or_default());
    keyring::Entry::new(KEYRING_SERVICE, &host).map_err(|e| e.to_string())
}

pub fn set_token(url: &str, token: &str) -> Result<(), String> {
    let entry = keyring_entry(url)?;
    if token.is_empty() {
        return match entry.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(e.to_string()),
        };
    }
    entry.set_password(token).map_err(|e| e.to_string())
}

pub fn has_token(url: &str) -> bool {
    keyring_entry(url).and_then(|e| e.get_password().map_err(|e| e.to_string())).is_ok()
}

fn token_for(url: &str) -> Option<String> {
    keyring_entry(url).ok()?.get_password().ok()
}

fn callbacks(url: &str) -> RemoteCallbacks<'static> {
    let token = token_for(url);
    let mut tried_token = false;
    let mut tried_helper = false;
    let mut cb = RemoteCallbacks::new();
    cb.credentials(move |_url, username, allowed| {
        if allowed.contains(CredentialType::SSH_KEY) {
            return Cred::ssh_key_from_agent(username.unwrap_or("git"));
        }
        if allowed.contains(CredentialType::USER_PASS_PLAINTEXT) {
            if let (Some(token), false) = (&token, tried_token) {
                tried_token = true;
                // GitHub and GitLab both accept a PAT as the password with any username.
                return Cred::userpass_plaintext("x-access-token", token);
            }
            if !tried_helper {
                tried_helper = true;
                if let Ok(cred) = Cred::credential_helper(&git2::Config::open_default().unwrap_or_else(|_| git2::Config::new().unwrap()), _url, username) {
                    return Ok(cred);
                }
            }
        }
        Err(git2::Error::from_str("no credentials available; add a token for this library"))
    });
    cb
}

fn fetch_options(url: &str) -> FetchOptions<'static> {
    let mut fo = FetchOptions::new();
    fo.remote_callbacks(callbacks(url));
    fo
}

fn info(url: &str, path: &Path, repo: &Repository) -> Result<LibraryInfo, String> {
    let head = repo.head().map_err(|e| e.to_string())?;
    let commit = head.peel_to_commit().map_err(|e| e.to_string())?;
    Ok(LibraryInfo {
        url: url.to_string(),
        name: display_name(url),
        path: path.to_string_lossy().to_string(),
        commit: commit.id().to_string()[..12].to_string(),
        branch: head.shorthand().unwrap_or("HEAD").to_string(),
        synced_at: chrono_now(),
    })
}

fn chrono_now() -> String {
    // RFC 3339 without pulling in chrono: seconds since epoch is enough for "synced N min ago".
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    secs.to_string()
}

/// Clone the library if absent, otherwise fetch and fast-forward to the
/// remote's default branch. Local edits are discarded: the clone is a cache.
pub fn sync(url: &str) -> Result<LibraryInfo, String> {
    let path = libraries_root()?.join(slug(url)?);
    if !path.join(".git").exists() {
        std::fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
        let repo = RepoBuilder::new()
            .fetch_options(fetch_options(url))
            .clone(url, &path)
            .map_err(|e| format!("clone failed: {}", e.message()))?;
        return info(url, &path, &repo);
    }
    let repo = Repository::open(&path).map_err(|e| e.to_string())?;
    {
        let mut remote = repo.find_remote("origin").map_err(|e| e.to_string())?;
        remote
            .fetch(&[] as &[&str], Some(&mut fetch_options(url)), None)
            .map_err(|e| format!("fetch failed: {}", e.message()))?;
    }
    let fetch_head = repo.find_reference("FETCH_HEAD").map_err(|e| e.to_string())?;
    let target = repo.reference_to_annotated_commit(&fetch_head).map_err(|e| e.to_string())?;
    let object = repo.find_object(target.id(), None).map_err(|e| e.to_string())?;
    repo.reset(&object, git2::ResetType::Hard, None).map_err(|e| e.to_string())?;
    info(url, &path, &repo)
}

/// What is on disk without touching the network; None if never cloned.
pub fn status(url: &str) -> Result<Option<LibraryInfo>, String> {
    let path = libraries_root()?.join(slug(url)?);
    if !path.join(".git").exists() {
        return Ok(None);
    }
    let repo = Repository::open(&path).map_err(|e| e.to_string())?;
    info(url, &path, &repo).map(Some)
}

/// Whether the clone actually holds a registry the CLI can read.
pub fn has_registry(path: &str) -> bool {
    Path::new(path).join("registry.json").is_file()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slug_normalizes_https_and_ssh() {
        assert_eq!(slug("https://github.com/acme/skills.git").unwrap(), "github.com-acme-skills");
        assert_eq!(slug("https://gitlab.example.com/team/sub/skills/").unwrap(), "gitlab.example.com-team-sub-skills");
        assert_eq!(slug("git@github.com:acme/skills.git").unwrap(), "github.com-acme-skills");
        assert!(slug("not a url").is_err());
        assert!(slug("https://github.com").is_err());
    }

    /// Clone a local repository, add a commit upstream, sync again, and see
    /// the new commit — the same path a team library takes over HTTPS.
    #[test]
    fn sync_clones_then_fast_forwards() {
        let tmp = std::env::temp_dir().join(format!("agent-skills-lib-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        let upstream = tmp.join("upstream");
        std::fs::create_dir_all(&upstream).unwrap();
        let git = |args: &[&str]| {
            let out = std::process::Command::new("git").args(args).current_dir(&upstream).output().unwrap();
            assert!(out.status.success(), "git {:?}: {}", args, String::from_utf8_lossy(&out.stderr));
        };
        git(&["init", "-q", "-b", "main"]);
        git(&["config", "user.email", "t@example.com"]);
        git(&["config", "user.name", "t"]);
        std::fs::write(upstream.join("registry.json"), "{\"skills\": []}\n").unwrap();
        git(&["add", "."]);
        git(&["commit", "-q", "-m", "one"]);

        std::env::set_var("AGENT_SKILLS_HOME", tmp.join("home"));
        // from_file_path yields file:///C:/... on Windows and file:///tmp/... elsewhere.
        let url = url::Url::from_file_path(upstream.canonicalize().unwrap()).unwrap().to_string();
        let first = sync(&url).unwrap();
        assert!(has_registry(&first.path));
        assert_eq!(first.branch, "main");

        std::fs::write(upstream.join("registry.json"), "{\"skills\": [1]}\n").unwrap();
        git(&["commit", "-q", "-am", "two"]);
        let second = sync(&url).unwrap();
        assert_ne!(first.commit, second.commit);
        assert_eq!(std::fs::read_to_string(Path::new(&second.path).join("registry.json")).unwrap(), "{\"skills\": [1]}\n");
        assert_eq!(status(&url).unwrap().unwrap().commit, second.commit);

        std::env::remove_var("AGENT_SKILLS_HOME");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn display_name_is_last_segment() {
        assert_eq!(display_name("https://github.com/acme/team-skills.git"), "team-skills");
        assert_eq!(display_name("git@github.com:acme/skills"), "skills");
    }
}
