use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuickAccessFolder {
    pub id: String,
    pub name: String,
    pub path: String,
    pub icon: String,
    pub count: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FsEntry {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size_bytes: u64,
    pub modified_ts: u64,
    pub ext: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DirContentResponse {
    pub current_path: String,
    pub parent_path: Option<String>,
    pub entries: Vec<FsEntry>,
}

fn get_home_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        if let Ok(profile) = std::env::var("USERPROFILE") {
            return PathBuf::from(profile);
        }
        if let (Ok(drive), Ok(path)) = (std::env::var("HOMEDRIVE"), std::env::var("HOMEPATH")) {
            return PathBuf::from(format!("{}{}", drive, path));
        }
        PathBuf::from("C:\\")
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home);
        }
        PathBuf::from("/")
    }
}

fn count_items(path: &Path) -> usize {
    if let Ok(entries) = fs::read_dir(path) {
        entries.filter_map(|e| e.ok()).count()
    } else {
        0
    }
}

pub fn get_quick_access_folders() -> Vec<QuickAccessFolder> {
    let mut folders = Vec::new();
    let home = get_home_dir();

    let candidates = [
        ("desktop", "Desktop", "desktop-outline", home.join("Desktop")),
        ("downloads", "Downloads", "download-outline", home.join("Downloads")),
        ("documents", "Documents", "document-text-outline", home.join("Documents")),
        ("pictures", "Pictures", "image-outline", home.join("Pictures")),
        ("videos", "Videos", "film-outline", home.join("Videos")),
        ("music", "Music", "musical-notes-outline", home.join("Music")),
    ];

    for (id, name, icon, path) in candidates {
        if path.exists() && path.is_dir() {
            let count = count_items(&path);
            folders.push(QuickAccessFolder {
                id: id.to_string(),
                name: name.to_string(),
                path: path.to_string_lossy().to_string(),
                icon: icon.to_string(),
                count: format!("{} items", count),
            });
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Detect mounted drive roots like C:\ and D:\
        for drive_letter in b'C'..=b'Z' {
            let drive_str = format!("{}:\\", drive_letter as char);
            let drive_path = Path::new(&drive_str);
            if drive_path.exists() {
                let name = if drive_letter == b'C' {
                    "Local Disk (C:)".to_string()
                } else {
                    format!("Drive ({}:)", drive_letter as char)
                };
                let count = count_items(drive_path);
                folders.push(QuickAccessFolder {
                    id: format!("drive_{}", (drive_letter as char).to_lowercase()),
                    name,
                    path: drive_str,
                    icon: "hardware-chip-outline".to_string(),
                    count: format!("{} items", count),
                });
            }
        }
    }

    folders
}

pub fn list_directory(raw_path: &str) -> Result<DirContentResponse, String> {
    let target_path = if raw_path.trim().is_empty() {
        get_home_dir()
    } else {
        PathBuf::from(raw_path.trim())
    };

    if !target_path.exists() {
        return Err(format!("Path does not exist: {}", target_path.display()));
    }

    if !target_path.is_dir() {
        return Err(format!("Path is not a directory: {}", target_path.display()));
    }

    let entries_iter = match fs::read_dir(&target_path) {
        Ok(iter) => iter,
        Err(e) => return Err(format!("Cannot read directory: {}", e)),
    };

    let mut entries = Vec::new();

    for item in entries_iter.filter_map(|e| e.ok()) {
        let path = item.path();
        let name = item.file_name().to_string_lossy().to_string();

        // Skip hidden system files if starting with dot or desktop.ini
        if name.starts_with('.') || name.eq_ignore_ascii_case("desktop.ini") {
            continue;
        }

        let is_dir = path.is_dir();
        let metadata = path.metadata().ok();
        let size_bytes = if is_dir {
            0
        } else {
            metadata.as_ref().map(|m| m.len()).unwrap_or(0)
        };

        let modified_ts = metadata
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);

        let ext = if is_dir {
            String::new()
        } else {
            path.extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_lowercase()
        };

        entries.push(FsEntry {
            name,
            path: path.to_string_lossy().to_string(),
            is_dir,
            size_bytes,
            modified_ts,
            ext,
        });
    }

    // Sort: directories first (case-insensitive name), then files
    entries.sort_by(|a, b| {
        match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    let current_path = target_path.to_string_lossy().to_string();
    let parent_path = target_path
        .parent()
        .map(|p| p.to_string_lossy().to_string());

    Ok(DirContentResponse {
        current_path,
        parent_path,
        entries,
    })
}

pub fn get_recent_files() -> Vec<FsEntry> {
    let home = get_home_dir();
    let search_roots = [
        home.join("Downloads"),
        home.join("Documents"),
        home.join("Desktop"),
    ];

    let mut all_files = Vec::new();

    for root in search_roots {
        if !root.exists() || !root.is_dir() {
            continue;
        }

        if let Ok(iter) = fs::read_dir(&root) {
            for entry in iter.filter_map(|e| e.ok()) {
                let path = entry.path();
                if path.is_file() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name.starts_with('.') || name.eq_ignore_ascii_case("desktop.ini") {
                        continue;
                    }

                    if let Ok(metadata) = path.metadata() {
                        let modified_ts = metadata
                            .modified()
                            .ok()
                            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                            .map(|d| d.as_secs())
                            .unwrap_or(0);

                        let ext = path
                            .extension()
                            .and_then(|s| s.to_str())
                            .unwrap_or("")
                            .to_lowercase();

                        all_files.push(FsEntry {
                            name,
                            path: path.to_string_lossy().to_string(),
                            is_dir: false,
                            size_bytes: metadata.len(),
                            modified_ts,
                            ext,
                        });
                    }
                }
            }
        }
    }

    // Sort by modified timestamp descending
    all_files.sort_by(|a, b| b.modified_ts.cmp(&a.modified_ts));
    all_files.truncate(30);

    all_files
}

pub fn search_files(query: &str, start_path: Option<&str>) -> Vec<FsEntry> {
    let q = query.trim().to_lowercase();
    if q.is_empty() {
        return Vec::new();
    }

    let root = match start_path {
        Some(p) if !p.trim().is_empty() && Path::new(p).exists() => PathBuf::from(p.trim()),
        _ => get_home_dir(),
    };

    let mut results = Vec::new();
    let mut queue = vec![(root, 0usize)];

    while let Some((dir, depth)) = queue.pop() {
        if depth > 4 || results.len() >= 50 {
            break;
        }

        if let Ok(iter) = fs::read_dir(&dir) {
            for entry in iter.filter_map(|e| e.ok()) {
                let path = entry.path();
                let name = entry.file_name().to_string_lossy().to_string();

                if name.starts_with('.')
                    || name.eq_ignore_ascii_case("node_modules")
                    || name.eq_ignore_ascii_case("target")
                    || name.eq_ignore_ascii_case("AppData")
                    || name.eq_ignore_ascii_case("desktop.ini")
                {
                    continue;
                }

                let is_dir = path.is_dir();
                if name.to_lowercase().contains(&q) {
                    let metadata = path.metadata().ok();
                    let size_bytes = if is_dir { 0 } else { metadata.as_ref().map(|m| m.len()).unwrap_or(0) };
                    let modified_ts = metadata
                        .and_then(|m| m.modified().ok())
                        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                        .map(|d| d.as_secs())
                        .unwrap_or(0);
                    let ext = if is_dir {
                        String::new()
                    } else {
                        path.extension()
                            .and_then(|s| s.to_str())
                            .unwrap_or("")
                            .to_lowercase()
                    };

                    results.push(FsEntry {
                        name,
                        path: path.to_string_lossy().to_string(),
                        is_dir,
                        size_bytes,
                        modified_ts,
                        ext,
                    });

                    if results.len() >= 50 {
                        break;
                    }
                }

                if is_dir && depth < 4 {
                    queue.push((path, depth + 1));
                }
            }
        }
    }

    results
}

pub fn open_file_on_pc(raw_path: &str) -> Result<(), String> {
    let path = raw_path.trim();
    if path.is_empty() {
        return Err("Path is empty".to_string());
    }

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(&["/C", "start", "", path])
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("Failed to open file: {}", e))
    }

    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(path)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("Failed to open file: {}", e))
    }

    #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("Failed to open file: {}", e))
    }
}

pub fn read_file_base64(raw_path: &str, max_bytes: u64) -> Result<(String, String, u64), String> {
    use base64::{engine::general_purpose::STANDARD, Engine as _};

    let path = Path::new(raw_path.trim());
    if !path.exists() {
        return Err(format!("File does not exist: {}", path.display()));
    }
    if path.is_dir() {
        return Err("Cannot open a folder as a file".to_string());
    }
    let metadata = fs::metadata(path).map_err(|e| format!("Cannot read file metadata: {}", e))?;
    let size = metadata.len();
    if size > max_bytes {
        return Err(format!(
            "File size ({}) exceeds mobile transfer limit of {}",
            crate::file_transfer::human_bytes(size),
            crate::file_transfer::human_bytes(max_bytes)
        ));
    }
    let bytes = fs::read(path).map_err(|e| format!("Failed to read file: {}", e))?;
    let b64 = STANDARD.encode(&bytes);
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("file")
        .to_string();
    Ok((name, b64, size))
}
