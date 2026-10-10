use crate::protocol::models::{CaptureResult, WindowBounds};
use anyhow::{bail, Context, Result};
use std::path::PathBuf;
use std::time::Instant;
use tokio::process::Command;
use tracing::{debug, info};

pub struct ScreenCapturer {
    cache_dir: PathBuf,
}

impl ScreenCapturer {
    pub fn new() -> Self {
        let cache_dir = dirs_cache_dir().join("blinky").join("captures");
        std::fs::create_dir_all(&cache_dir).ok();
        Self { cache_dir }
    }

    pub fn with_cache_dir(cache_dir: PathBuf) -> Self {
        std::fs::create_dir_all(&cache_dir).ok();
        Self { cache_dir }
    }

    fn new_capture_path(&self, prefix: &str, ext: &str) -> PathBuf {
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis();
        self.cache_dir.join(format!("{}-{}.{}", prefix, ts, ext))
    }

    pub async fn capture_fullscreen(&self, monitor_name: Option<&str>) -> Result<CaptureResult> {
        let start = Instant::now();
        let target_path = self.new_capture_path("screen", "jpg");

        let mut cmd = Command::new("grim");
        cmd.args(["-t", "jpeg", "-q", "80"]);
        if let Some(mon) = monitor_name {
            cmd.args(["-o", mon]);
        }
        cmd.arg(&target_path);

        let output = cmd
            .output()
            .await
            .context("Failed to spawn grim for fullscreen capture")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            bail!("grim fullscreen capture failed: {}", stderr);
        }

        let metadata = std::fs::metadata(&target_path)
            .with_context(|| format!("Captured image not found at {}", target_path.display()))?;
        if metadata.len() == 0 {
            bail!("grim produced an empty 0-byte file");
        }

        let (width, height) = Self::read_dimensions(&target_path)?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

        info!(
            "Captured fullscreen: {} ({}x{}) in {:.2}ms",
            target_path.display(),
            width,
            height,
            elapsed_ms
        );

        Ok(CaptureResult {
            path: target_path.to_string_lossy().to_string(),
            width,
            height,
            screen_width: width,
            screen_height: height,
            scale: 1.0,
            elapsed_ms,
            frame: None,
        })
    }

    pub async fn capture_window_crop(
        &self,
        bounds: &WindowBounds,
        scale: f64,
    ) -> Result<CaptureResult> {
        let start = Instant::now();
        let target_path = self.new_capture_path("window", "jpg");

        let phys_x = (bounds.x as f64 * scale).round() as i32;
        let phys_y = (bounds.y as f64 * scale).round() as i32;
        let phys_w = (bounds.width as f64 * scale).round() as u32;
        let phys_h = (bounds.height as f64 * scale).round() as u32;

        let geom = format!("{},{} {}x{}", phys_x, phys_y, phys_w, phys_h);
        debug!("Executing grim window crop with geometry: {}", geom);

        let output = Command::new("grim")
            .args(["-t", "jpeg", "-q", "80", "-g", &geom])
            .arg(&target_path)
            .output()
            .await
            .context("Failed to spawn grim for window crop")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            bail!("grim window crop failed for geom '{}': {}", geom, stderr);
        }

        let (width, height) = Self::read_dimensions(&target_path)?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

        info!(
            "Captured window crop: {} ({}x{}) in {:.2}ms",
            target_path.display(),
            width,
            height,
            elapsed_ms
        );

        Ok(CaptureResult {
            path: target_path.to_string_lossy().to_string(),
            width,
            height,
            screen_width: phys_w,
            screen_height: phys_h,
            scale,
            elapsed_ms,
            frame: None,
        })
    }

    pub async fn capture_interactive(&self) -> Result<CaptureResult> {
        let start = Instant::now();
        let target_path = self.new_capture_path("interactive", "jpg");

        // 1. Run slurp to get geometry selection from user
        let slurp_output = Command::new("slurp")
            .output()
            .await
            .context("Failed to run slurp for interactive region selection")?;

        if !slurp_output.status.success() {
            bail!("Interactive region selection cancelled or failed");
        }

        let geom = String::from_utf8_lossy(&slurp_output.stdout).trim().to_string();
        if geom.is_empty() {
            bail!("No region selected in slurp");
        }

        // 2. Capture with grim
        let output = Command::new("grim")
            .args(["-t", "jpeg", "-q", "80", "-g", &geom])
            .arg(&target_path)
            .output()
            .await
            .context("Failed to run grim for interactive region capture")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            bail!("grim interactive capture failed: {}", stderr);
        }

        let (width, height) = Self::read_dimensions(&target_path)?;
        let elapsed_ms = start.elapsed().as_secs_f64() * 1000.0;

        Ok(CaptureResult {
            path: target_path.to_string_lossy().to_string(),
            width,
            height,
            screen_width: width,
            screen_height: height,
            scale: 1.0,
            elapsed_ms,
            frame: None,
        })
    }

    fn read_dimensions(path: &PathBuf) -> Result<(u32, u32)> {
        let reader = image::ImageReader::open(path)
            .with_context(|| format!("Failed to open image at {}", path.display()))?
            .with_guessed_format()
            .with_context(|| format!("Failed to guess image format for {}", path.display()))?
            .into_dimensions()
            .with_context(|| format!("Failed to decode dimensions for {}", path.display()))?;
        Ok(reader)
    }
}

fn dirs_cache_dir() -> PathBuf {
    if let Ok(path) = std::env::var("XDG_CACHE_HOME") {
        PathBuf::from(path)
    } else if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".cache")
    } else {
        PathBuf::from("/tmp")
    }
}
