use serde_json::{json, Value};
#[cfg(target_os = "linux")]
use std::fs;
#[cfg(target_os = "linux")]
use std::path::Path;

/// Collects host identity, uptime, memory, battery, and network telemetry.
pub fn get_system_telemetry() -> Value {
    #[cfg(target_os = "linux")]
    {
        // 1. Hostname (RFC 1123 host)
        let hostname = fs::read_to_string("/etc/hostname")
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|_| std::env::var("HOSTNAME").unwrap_or_else(|_| "Blinky-Host".to_string()));

        // 2. OS Name — freedesktop.org standard (/etc/os-release, fallback /usr/lib/os-release)
        let os_name = fs::read_to_string("/etc/os-release")
            .or_else(|_| fs::read_to_string("/usr/lib/os-release"))
            .ok()
            .and_then(|content| {
                for line in content.lines() {
                    if line.starts_with("PRETTY_NAME=") {
                        let val = line.trim_start_matches("PRETTY_NAME=").trim_matches('"');
                        return Some(val.to_string());
                    }
                }
                None
            })
            .unwrap_or_else(|| "Linux".to_string());

        // 3. Desktop / Compositor (Hyprland, Sway, KDE Plasma, GNOME, XFCE, etc.)
        let desktop = std::env::var("XDG_CURRENT_DESKTOP")
            .or_else(|_| std::env::var("DESKTOP_SESSION"))
            .or_else(|_| std::env::var("XDG_SESSION_DESKTOP"))
            .unwrap_or_else(|_| "Desktop".to_string());
        let session_type = std::env::var("XDG_SESSION_TYPE").unwrap_or_default();
        let compositor = if !session_type.is_empty() {
            format!("{} ({})", desktop, session_type)
        } else {
            desktop
        };

        // 4. System Uptime from /proc/uptime (standard on all Linux kernels)
        let uptime_seconds = fs::read_to_string("/proc/uptime")
            .ok()
            .and_then(|content| {
                content
                    .split_whitespace()
                    .next()
                    .and_then(|s| s.parse::<f64>().ok())
                    .map(|f| f as u64)
            })
            .unwrap_or(0);

        // 5. Memory statistics from /proc/meminfo
        let (total_mb, used_mb, mem_percent) = fs::read_to_string("/proc/meminfo")
            .ok()
            .and_then(|content| {
                let mut total_kb = 0u64;
                let mut avail_kb = 0u64;
                for line in content.lines() {
                    if line.starts_with("MemTotal:") {
                        total_kb = parse_meminfo_kb(line);
                    } else if line.starts_with("MemAvailable:") {
                        avail_kb = parse_meminfo_kb(line);
                    }
                }
                if total_kb > 0 {
                    let used_kb = total_kb.saturating_sub(avail_kb);
                    let percent = ((used_kb as f64 / total_kb as f64) * 100.0) as u32;
                    Some((total_kb / 1024, used_kb / 1024, percent))
                } else {
                    None
                }
            })
            .unwrap_or((0, 0, 0));

        let battery = read_linux_battery();
        let network = read_linux_network();

        json!({
            "type": "system_info",
            "hostname": hostname,
            "os": os_name,
            "platform": "linux",
            "compositor": compositor,
            "uptime_seconds": uptime_seconds,
            "memory": {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "percent": mem_percent
            },
            "battery": battery,
            "network": network,
            "version": "0.1.0",
            "is_locked": crate::platform::is_workstation_locked()
        })
    }

    #[cfg(target_os = "windows")]
    {
        let hostname = std::env::var("COMPUTERNAME").unwrap_or_else(|_| "Windows-PC".to_string());
        let (os_name, total_mb, used_mb, mem_percent, uptime_seconds, battery, network) = read_windows_telemetry();

        json!({
            "type": "system_info",
            "hostname": hostname,
            "os": os_name,
            "platform": "windows",
            "compositor": "Windows Desktop (DWM)",
            "uptime_seconds": uptime_seconds,
            "memory": {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "percent": mem_percent
            },
            "battery": battery,
            "network": network,
            "version": "0.1.0",
            "is_locked": crate::platform::is_workstation_locked()
        })
    }
}

/// Parses a `/proc/meminfo` value expressed in kilobytes.
#[cfg(target_os = "linux")]
fn parse_meminfo_kb(line: &str) -> u64 {
    line.split_whitespace()
        .nth(1)
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(0)
}

/// Reads battery capacity and charging state from Linux sysfs.
#[cfg(target_os = "linux")]
fn read_linux_battery() -> Value {
    let power_path = Path::new("/sys/class/power_supply");
    if let Ok(entries) = fs::read_dir(power_path) {
        for entry in entries.flatten() {
            let p = entry.path();
            let p_type = fs::read_to_string(p.join("type")).unwrap_or_default();
            if p_type.trim().eq_ignore_ascii_case("battery") || entry.file_name().to_string_lossy().starts_with("BAT") {
                let capacity = fs::read_to_string(p.join("capacity"))
                    .ok()
                    .and_then(|c| c.trim().parse::<u32>().ok());
                let status = fs::read_to_string(p.join("status"))
                    .map(|s| s.trim().to_string())
                    .unwrap_or_else(|_| "Unknown".to_string());
                let is_charging = status.eq_ignore_ascii_case("charging");
                return json!({
                    "has_battery": true,
                    "percent": capacity,
                    "is_charging": is_charging,
                    "status": status
                });
            }
        }
    }

    json!({
        "has_battery": false,
        "percent": null,
        "is_charging": false,
        "status": "AC Mains Nominal"
    })
}

/// Selects an active physical network interface and reports its MAC address.
#[cfg(target_os = "linux")]
fn read_linux_network() -> Value {
    let net_path = Path::new("/sys/class/net");
    let mut best_mac = String::new();
    let mut best_iface = String::new();

    if let Ok(entries) = fs::read_dir(net_path) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name == "lo" || name.starts_with("docker") || name.starts_with("veth") || name.starts_with("br-") || name.starts_with("tailscale") {
                continue;
            }

            let p = entry.path();
            let mac = fs::read_to_string(p.join("address")).unwrap_or_default().trim().to_string();
            let oper = fs::read_to_string(p.join("operstate")).unwrap_or_default().trim().to_string();

            if !mac.is_empty() && mac != "00:00:00:00:00:00" {
                if oper == "up" || best_mac.is_empty() {
                    best_mac = mac;
                    best_iface = name;
                    if oper == "up" {
                        break;
                    }
                }
            }
        }
    }

    json!({
        "mac_address": best_mac,
        "interface": best_iface
    })
}

/// Returns the currently supported Windows telemetry fields including memory, uptime, battery, and physical network MAC.
#[cfg(target_os = "windows")]
fn read_windows_telemetry() -> (String, u64, u64, u32, u64, Value, Value) {
    let os_name = "Windows".to_string();

    // 1. Memory stats via GlobalMemoryStatusEx
    let (total_mb, used_mb, mem_percent) = unsafe {
        let mut mem: windows_sys::Win32::System::SystemInformation::MEMORYSTATUSEX = std::mem::zeroed();
        mem.dwLength = std::mem::size_of::<windows_sys::Win32::System::SystemInformation::MEMORYSTATUSEX>() as u32;
        if windows_sys::Win32::System::SystemInformation::GlobalMemoryStatusEx(&mut mem) != 0 {
            let total = mem.ullTotalPhys / (1024 * 1024);
            let avail = mem.ullAvailPhys / (1024 * 1024);
            let used = total.saturating_sub(avail);
            (total, used, mem.dwMemoryLoad)
        } else {
            (0, 0, 0)
        }
    };

    // 2. System uptime via GetTickCount64
    let uptime_seconds = unsafe {
        windows_sys::Win32::System::SystemInformation::GetTickCount64() / 1000
    };

    // 3. Battery stats via GetSystemPowerStatus
    let battery = unsafe {
        let mut power: windows_sys::Win32::System::Power::SYSTEM_POWER_STATUS = std::mem::zeroed();
        if windows_sys::Win32::System::Power::GetSystemPowerStatus(&mut power) != 0 {
            let has_battery = power.BatteryFlag != 128 && power.BatteryFlag != 255;
            let percent = if power.BatteryLifePercent <= 100 {
                Some(power.BatteryLifePercent as u32)
            } else {
                None
            };
            let is_charging = (power.BatteryFlag & 8) != 0;
            let status = if !has_battery {
                "AC Mains Nominal".to_string()
            } else if is_charging {
                "Charging".to_string()
            } else {
                "Discharging".to_string()
            };
            json!({
                "has_battery": has_battery,
                "percent": percent,
                "is_charging": is_charging,
                "status": status
            })
        } else {
            json!({
                "has_battery": false,
                "percent": null,
                "is_charging": false,
                "status": "AC Mains Nominal"
            })
        }
    };

    // 4. Physical network adapter and MAC address
    let network = read_windows_network();

    (os_name, total_mb, used_mb, mem_percent, uptime_seconds, battery, network)
}

/// Reads the active physical network adapter MAC address and name on Windows.
#[cfg(target_os = "windows")]
fn read_windows_network() -> Value {
    use std::sync::Mutex;
    use std::time::{Duration, Instant};

    static NET_CACHE: Mutex<Option<(Instant, String, String)>> = Mutex::new(None);

    if let Ok(mut guard) = NET_CACHE.lock() {
        if let Some((cached_at, ref mac, ref iface)) = *guard {
            if !mac.is_empty() && cached_at.elapsed() < Duration::from_secs(30) {
                return json!({
                    "mac_address": mac,
                    "interface": iface
                });
            }
        }

        let (mac, iface) = query_windows_mac_and_iface();
        *guard = Some((Instant::now(), mac.clone(), iface.clone()));
        return json!({
            "mac_address": mac,
            "interface": iface
        });
    }

    let (mac, iface) = query_windows_mac_and_iface();
    json!({
        "mac_address": mac,
        "interface": iface
    })
}

/// Discovers active physical network adapter MAC using getmac with PowerShell WMI fallback.
#[cfg(target_os = "windows")]
fn query_windows_mac_and_iface() -> (String, String) {
    use std::process::Command;
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    // 1. Fast path: getmac /fo csv /nh
    if let Ok(output) = Command::new("getmac")
        .args(["/fo", "csv", "/nh"])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            for line in text.lines() {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }
                let parts: Vec<&str> = trimmed
                    .split(',')
                    .map(|p| p.trim().trim_matches('"'))
                    .collect();
                if parts.len() >= 2 {
                    let mac = parts[0];
                    let transport = parts[1];
                    if mac != "N/A"
                        && !mac.is_empty()
                        && !transport.to_lowercase().contains("disconnected")
                    {
                        let clean_mac = mac.replace('-', ":").to_lowercase();
                        if clean_mac.split(':').count() == 6 {
                            let iface = if transport.contains("Tcpip") {
                                "Wi-Fi / Ethernet".to_string()
                            } else {
                                transport.to_string()
                            };
                            return (clean_mac, iface);
                        }
                    }
                }
            }
        }
    }

    // 2. Fallback: PowerShell WMI query for active adapter MAC
    if let Ok(output) = Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = TRUE and MACAddress IS NOT NULL' | Select-Object -ExpandProperty MACAddress -First 1",
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        if output.status.success() {
            let mac = String::from_utf8_lossy(&output.stdout).trim().to_lowercase();
            if mac.split(':').count() == 6 {
                return (mac, "Physical Adapter".to_string());
            }
        }
    }

    (String::new(), String::new())
}
