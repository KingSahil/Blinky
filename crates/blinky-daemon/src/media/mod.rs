use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use tokio::process::Command;
use tracing::{debug, info};
use zbus::zvariant::OwnedValue;
use zbus::Connection;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct MediaMetadata {
    pub title: String,
    pub artist: String,
    pub album: String,
    pub art_url: String,
    pub track_id: String,
    pub length_seconds: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MediaState {
    pub status: String, // "Playing", "Paused", "Stopped"
    pub player_name: String,
    pub metadata: MediaMetadata,
}

pub struct MediaController {
    session_conn: Option<Connection>,
}

impl MediaController {
    pub async fn new() -> Self {
        let session_conn = Connection::session().await.ok();
        Self { session_conn }
    }

    async fn find_active_player(&self) -> Result<String> {
        let conn = self
            .session_conn
            .as_ref()
            .context("No session D-Bus connection")?;

        let names: Vec<String> = conn
            .call_method(
                Some("org.freedesktop.DBus"),
                "/org/freedesktop/DBus",
                Some("org.freedesktop.DBus"),
                "ListNames",
                &(),
            )
            .await?
            .body()
            .deserialize()?;

        let mut players: Vec<String> = names
            .into_iter()
            .filter(|n| n.starts_with("org.mpris.MediaPlayer2."))
            .collect();

        if players.is_empty() {
            bail!("No active MPRIS media players found");
        }

        players.sort_by_key(|n| {
            if n.contains("spotify") {
                0
            } else if n.contains("vivaldi") || n.contains("chrome") || n.contains("firefox") {
                1
            } else {
                2
            }
        });

        Ok(players[0].clone())
    }

    pub async fn play_pause(&self) -> Result<()> {
        info!("Toggling media Play/Pause");
        if let Ok(player) = self.find_active_player().await {
            if let Some(conn) = &self.session_conn {
                let res: Result<(), zbus::Error> = conn
                    .call_method(
                        Some(player.as_str()),
                        "/org/mpris/MediaPlayer2",
                        Some("org.mpris.MediaPlayer2.Player"),
                        "PlayPause",
                        &(),
                    )
                    .await
                    .map(|_| ());
                if res.is_ok() {
                    return Ok(());
                }
            }
        }

        let status = Command::new("playerctl")
            .arg("play-pause")
            .status()
            .await
            .context("Failed to spawn playerctl play-pause")?;

        if !status.success() {
            debug!("playerctl play-pause returned non-zero");
        }
        Ok(())
    }

    pub async fn next(&self) -> Result<()> {
        info!("Media Next Track");
        if let Ok(player) = self.find_active_player().await {
            if let Some(conn) = &self.session_conn {
                let res: Result<(), zbus::Error> = conn
                    .call_method(
                        Some(player.as_str()),
                        "/org/mpris/MediaPlayer2",
                        Some("org.mpris.MediaPlayer2.Player"),
                        "Next",
                        &(),
                    )
                    .await
                    .map(|_| ());
                if res.is_ok() {
                    return Ok(());
                }
            }
        }

        Command::new("playerctl").arg("next").status().await.ok();
        Ok(())
    }

    pub async fn previous(&self) -> Result<()> {
        info!("Media Previous Track");
        if let Ok(player) = self.find_active_player().await {
            if let Some(conn) = &self.session_conn {
                let res: Result<(), zbus::Error> = conn
                    .call_method(
                        Some(player.as_str()),
                        "/org/mpris/MediaPlayer2",
                        Some("org.mpris.MediaPlayer2.Player"),
                        "Previous",
                        &(),
                    )
                    .await
                    .map(|_| ());
                if res.is_ok() {
                    return Ok(());
                }
            }
        }

        Command::new("playerctl").arg("previous").status().await.ok();
        Ok(())
    }

    pub async fn get_state(&self) -> Result<MediaState> {
        let player = self.find_active_player().await?;
        let conn = self
            .session_conn
            .as_ref()
            .context("No session D-Bus connection")?;

        // 1. Get PlaybackStatus property (wrapped in Variant)
        let status_reply = conn
            .call_method(
                Some(player.as_str()),
                "/org/mpris/MediaPlayer2",
                Some("org.freedesktop.DBus.Properties"),
                "Get",
                &("org.mpris.MediaPlayer2.Player", "PlaybackStatus"),
            )
            .await?;

        let status_owned: OwnedValue = status_reply.body().deserialize()?;
        let status_str = match &*status_owned {
            zbus::zvariant::Value::Str(s) => s.to_string(),
            zbus::zvariant::Value::Value(inner) => match &**inner {
                zbus::zvariant::Value::Str(s) => s.to_string(),
                _ => "Unknown".to_string(),
            },
            _ => "Unknown".to_string(),
        };

        // 2. Get Metadata property
        let mut metadata = MediaMetadata::default();
        if let Ok(meta_reply) = conn
            .call_method(
                Some(player.as_str()),
                "/org/mpris/MediaPlayer2",
                Some("org.freedesktop.DBus.Properties"),
                "Get",
                &("org.mpris.MediaPlayer2.Player", "Metadata"),
            )
            .await
        {
            if let Ok(meta_owned) = meta_reply.body().deserialize::<OwnedValue>() {
                if let zbus::zvariant::Value::Dict(dict) = &*meta_owned {
                    for (k, v) in dict.iter() {
                        if let zbus::zvariant::Value::Str(key) = k {
                            match key.as_str() {
                                "xesam:title" => {
                                    if let zbus::zvariant::Value::Str(t) = v {
                                        metadata.title = t.to_string();
                                    }
                                }
                                "xesam:artist" => {
                                    if let zbus::zvariant::Value::Array(arr) = v {
                                        let artists: Vec<String> = arr
                                            .iter()
                                            .filter_map(|a| match a {
                                                zbus::zvariant::Value::Str(s) => Some(s.to_string()),
                                                _ => None,
                                            })
                                            .collect();
                                        metadata.artist = artists.join(", ");
                                    } else if let zbus::zvariant::Value::Str(a) = v {
                                        metadata.artist = a.to_string();
                                    }
                                }
                                "xesam:album" => {
                                    if let zbus::zvariant::Value::Str(al) = v {
                                        metadata.album = al.to_string();
                                    }
                                }
                                "mpris:artUrl" => {
                                    if let zbus::zvariant::Value::Str(u) = v {
                                        metadata.art_url = u.to_string();
                                    }
                                }
                                "mpris:trackid" => {
                                    if let zbus::zvariant::Value::ObjectPath(o) = v {
                                        metadata.track_id = o.to_string();
                                    } else if let zbus::zvariant::Value::Str(s) = v {
                                        metadata.track_id = s.to_string();
                                    }
                                }
                                "mpris:length" => {
                                    if let zbus::zvariant::Value::I64(l) = v {
                                        metadata.length_seconds = Some(*l as f64 / 1_000_000.0);
                                    } else if let zbus::zvariant::Value::U64(u) = v {
                                        metadata.length_seconds = Some(*u as f64 / 1_000_000.0);
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                }
            }
        }

        Ok(MediaState {
            status: status_str,
            player_name: player.replace("org.mpris.MediaPlayer2.", ""),
            metadata,
        })
    }

    async fn get_all_target_sinks(&self) -> Vec<String> {
        let mut sinks = vec!["@DEFAULT_SINK@".to_string()];

        // 1. Query full sink properties to catch physical hardware devices (PCI/USB/Bluetooth) and active DSP filters
        if let Ok(output) = Command::new("pactl").args(["list", "sinks"]).output().await {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                let mut current_name = String::new();
                let mut is_hardware_or_running = false;

                for line in text.lines() {
                    let trimmed = line.trim();
                    if line.starts_with("Sink #") {
                        if !current_name.is_empty() && is_hardware_or_running {
                            if !sinks.contains(&current_name) {
                                sinks.push(current_name);
                            }
                        }
                        current_name = String::new();
                        is_hardware_or_running = false;
                    } else if trimmed.starts_with("Name: ") {
                        current_name = trimmed["Name: ".len()..].trim().to_string();
                        // Physical alsa/bluez sinks or DSP filter sinks
                        if current_name.starts_with("alsa_output.")
                            || current_name.starts_with("bluez_output.")
                            || current_name.starts_with("bluez_sink.")
                            || current_name.contains("easyeffects")
                            || current_name.contains("jamesdsp")
                        {
                            is_hardware_or_running = true;
                        }
                    } else if trimmed.starts_with("State: RUNNING") {
                        is_hardware_or_running = true;
                    } else if trimmed == "device.class = \"sound\""
                        || trimmed.starts_with("device.bus = ")
                        || trimmed.starts_with("device.subsystem = \"sound\"")
                    {
                        is_hardware_or_running = true;
                    }
                }
                if !current_name.is_empty() && is_hardware_or_running {
                    if !sinks.contains(&current_name) {
                        sinks.push(current_name);
                    }
                }
            }
        }

        sinks
    }

    pub async fn volume_up(&self) -> Result<()> {
        let sinks = self.get_all_target_sinks().await;
        for s in sinks {
            let _ = Command::new("pactl")
                .args(["set-sink-volume", &s, "+5%"])
                .status()
                .await;
        }
        let _ = Command::new("wpctl")
            .args(["set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"])
            .status()
            .await;
        Ok(())
    }

    pub async fn volume_down(&self) -> Result<()> {
        let sinks = self.get_all_target_sinks().await;
        for s in sinks {
            let _ = Command::new("pactl")
                .args(["set-sink-volume", &s, "-5%"])
                .status()
                .await;
        }
        let _ = Command::new("wpctl")
            .args(["set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"])
            .status()
            .await;
        Ok(())
    }

    pub async fn volume_mute_toggle(&self) -> Result<()> {
        let sinks = self.get_all_target_sinks().await;
        for s in sinks {
            let _ = Command::new("pactl")
                .args(["set-sink-mute", &s, "toggle"])
                .status()
                .await;
        }
        let _ = Command::new("wpctl")
            .args(["set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
            .status()
            .await;
        Ok(())
    }
}
