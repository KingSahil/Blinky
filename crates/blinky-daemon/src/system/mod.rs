use anyhow::{Context, Result};
use tokio::process::Command;
use tracing::{debug, info, warn};
use zbus::Connection;

pub struct SystemSessionController {
    system_conn: Option<Connection>,
}

impl SystemSessionController {
    pub async fn new() -> Self {
        let system_conn = Connection::system().await.ok();
        Self { system_conn }
    }

    pub async fn lock(&self) -> Result<()> {
        info!("Executing session lock");
        // 1. Try D-Bus login1 LockSessions
        if let Some(conn) = &self.system_conn {
            let res: Result<(), zbus::Error> = conn
                .call_method(
                    Some("org.freedesktop.login1"),
                    "/org/freedesktop/login1",
                    Some("org.freedesktop.login1.Manager"),
                    "LockSessions",
                    &(),
                )
                .await
                .map(|_| ());
            if res.is_ok() {
                debug!("Session locked via D-Bus login1 LockSessions");
                return Ok(());
            }
        }

        // 2. Try Hyprland native lock
        let hypr_status = Command::new("hyprctl")
            .args(["dispatch", "lock"])
            .status()
            .await;
        if let Ok(st) = hypr_status {
            if st.success() {
                debug!("Session locked via hyprctl dispatch lock");
                return Ok(());
            }
        }

        // 3. Try loginctl lock-session
        let loginctl_status = Command::new("loginctl")
            .args(["lock-session"])
            .status()
            .await
            .context("Failed to spawn loginctl lock-session")?;

        if !loginctl_status.success() {
            warn!("loginctl lock-session returned non-zero status");
        }

        Ok(())
    }

    pub async fn suspend(&self) -> Result<()> {
        info!("Executing system suspend");
        if let Some(conn) = &self.system_conn {
            let res: Result<(), zbus::Error> = conn
                .call_method(
                    Some("org.freedesktop.login1"),
                    "/org/freedesktop/login1",
                    Some("org.freedesktop.login1.Manager"),
                    "Suspend",
                    &(true),
                )
                .await
                .map(|_| ());
            if res.is_ok() {
                return Ok(());
            }
        }

        Command::new("systemctl")
            .args(["suspend"])
            .status()
            .await
            .context("Failed to run systemctl suspend")?;
        Ok(())
    }

    pub async fn hibernate(&self) -> Result<()> {
        info!("Executing system hibernate");
        if let Some(conn) = &self.system_conn {
            let res: Result<(), zbus::Error> = conn
                .call_method(
                    Some("org.freedesktop.login1"),
                    "/org/freedesktop/login1",
                    Some("org.freedesktop.login1.Manager"),
                    "Hibernate",
                    &(true),
                )
                .await
                .map(|_| ());
            if res.is_ok() {
                return Ok(());
            }
        }

        Command::new("systemctl")
            .args(["hibernate"])
            .status()
            .await
            .context("Failed to run systemctl hibernate")?;
        Ok(())
    }

    pub async fn reboot(&self) -> Result<()> {
        info!("Executing system reboot");
        if let Some(conn) = &self.system_conn {
            let res: Result<(), zbus::Error> = conn
                .call_method(
                    Some("org.freedesktop.login1"),
                    "/org/freedesktop/login1",
                    Some("org.freedesktop.login1.Manager"),
                    "Reboot",
                    &(true),
                )
                .await
                .map(|_| ());
            if res.is_ok() {
                return Ok(());
            }
        }

        Command::new("systemctl")
            .args(["reboot"])
            .status()
            .await
            .context("Failed to run systemctl reboot")?;
        Ok(())
    }

    pub async fn power_off(&self) -> Result<()> {
        info!("Executing system power off");
        if let Some(conn) = &self.system_conn {
            let res: Result<(), zbus::Error> = conn
                .call_method(
                    Some("org.freedesktop.login1"),
                    "/org/freedesktop/login1",
                    Some("org.freedesktop.login1.Manager"),
                    "PowerOff",
                    &(true),
                )
                .await
                .map(|_| ());
            if res.is_ok() {
                return Ok(());
            }
        }

        Command::new("systemctl")
            .args(["poweroff"])
            .status()
            .await
            .context("Failed to run systemctl poweroff")?;
        Ok(())
    }
}
