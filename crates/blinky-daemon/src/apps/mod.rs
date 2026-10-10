use crate::protocol::models::AppEntry;
use anyhow::{bail, Context, Result};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::process::Command;
use tracing::{debug, info};

pub struct AppRegistry;

impl AppRegistry {
    pub fn list_desktop_dirs() -> Vec<PathBuf> {
        let mut dirs = Vec::new();
        if let Ok(home) = std::env::var("HOME") {
            dirs.push(
                PathBuf::from(&home)
                    .join(".local")
                    .join("share")
                    .join("applications"),
            );
        }
        dirs.push(PathBuf::from("/var/lib/flatpak/exports/share/applications"));
        dirs.push(PathBuf::from("/usr/local/share/applications"));
        dirs.push(PathBuf::from("/usr/share/applications"));
        dirs
    }

    pub fn scan_apps() -> Vec<AppEntry> {
        let mut entries: HashMap<String, AppEntry> = HashMap::new();

        for dir in Self::list_desktop_dirs() {
            if !dir.is_dir() {
                continue;
            }
            if let Ok(read_dir) = std::fs::read_dir(&dir) {
                for file_entry in read_dir.flatten() {
                    let path = file_entry.path();
                    if path.extension().and_then(|s| s.to_str()) == Some("desktop") {
                        if let Some(app) = Self::parse_desktop_file(&path) {
                            // Earlier directories take precedence over later directories
                            entries.entry(app.desktop_id.clone()).or_insert(app);
                        }
                    }
                }
            }
        }

        let mut list: Vec<AppEntry> = entries.into_values().collect();
        list.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
        list
    }

    pub fn parse_desktop_file(path: &Path) -> Option<AppEntry> {
        let content = std::fs::read_to_string(path).ok()?;
        let mut in_main_section = false;

        let mut name = String::new();
        let mut exec = String::new();
        let mut wm_class = String::new();
        let mut icon = String::new();
        let mut categories = Vec::new();
        let mut no_display = false;
        let mut hidden = false;

        for line in content.lines() {
            let line = line.trim();
            if line.starts_with('[') {
                in_main_section = line == "[Desktop Entry]";
                continue;
            }
            if !in_main_section || line.starts_with('#') || !line.contains('=') {
                continue;
            }

            let mut split = line.splitn(2, '=');
            let key = split.next()?.trim();
            let value = split.next()?.trim();

            match key {
                "Name" if name.is_empty() => name = value.to_string(),
                "Exec" if exec.is_empty() => exec = value.to_string(),
                "StartupWMClass" if wm_class.is_empty() => wm_class = value.to_string(),
                "Icon" if icon.is_empty() => icon = value.to_string(),
                "NoDisplay" => no_display = value.eq_ignore_ascii_case("true"),
                "Hidden" => hidden = value.eq_ignore_ascii_case("true"),
                "Categories" => {
                    categories = value
                        .split(';')
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty())
                        .collect();
                }
                _ => {}
            }
        }

        if name.is_empty() || exec.is_empty() || no_display || hidden {
            return None;
        }

        let desktop_id = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();

        let path_str = path.to_string_lossy().to_string();
        let source = if path_str.contains("flatpak") {
            "flatpak"
        } else if path_str.contains(".local") {
            "user"
        } else {
            "system"
        };

        Some(AppEntry {
            name,
            desktop_id,
            exec_line: exec,
            path: path_str,
            startup_wm_class: wm_class,
            categories,
            icon,
            source: source.to_string(),
        })
    }

    pub fn find_app(query: &str) -> Option<AppEntry> {
        let apps = Self::scan_apps();
        let q = query.trim().to_lowercase();

        // 1. Exact desktop_id match (e.g. "code", "spotify")
        if let Some(app) = apps.iter().find(|a| a.desktop_id.to_lowercase() == q) {
            return Some(app.clone());
        }

        // 2. Exact name match
        if let Some(app) = apps.iter().find(|a| a.name.to_lowercase() == q) {
            return Some(app.clone());
        }

        // 3. Substring match on name or desktop_id
        if let Some(app) = apps.iter().find(|a| {
            a.name.to_lowercase().contains(&q) || a.desktop_id.to_lowercase().contains(&q)
        }) {
            return Some(app.clone());
        }

        None
    }

    pub async fn launch(query: &str) -> Result<AppEntry> {
        let app = Self::find_app(query)
            .with_context(|| format!("No application matching '{}' found in desktop registry", query))?;

        info!("Launching application '{}' from {}", app.name, app.path);

        // Try gio launch first
        let gio_status = Command::new("gio")
            .args(["launch", &app.path])
            .status()
            .await;

        if let Ok(status) = gio_status {
            if status.success() {
                debug!("Launched via gio launch: {}", app.name);
                return Ok(app);
            }
        }

        // Fallback: spawn sanitized exec
        let sanitized = app
            .exec_line
            .replace("%u", "")
            .replace("%U", "")
            .replace("%f", "")
            .replace("%F", "")
            .replace("%i", "")
            .replace("%c", "")
            .replace("%k", "");
        let parts: Vec<&str> = sanitized.split_whitespace().collect();
        if parts.is_empty() {
            bail!("Empty Exec line for app: {}", app.name);
        }

        Command::new(parts[0])
            .args(&parts[1..])
            .spawn()
            .with_context(|| format!("Failed to spawn process for {}", app.name))?;

        Ok(app)
    }
}
