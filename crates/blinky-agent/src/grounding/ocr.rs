use anyhow::{Context, Result};
use blinky_daemon::protocol::models::UIElement;
use tokio::process::Command;
use tracing::debug;

pub struct OcrGrounder;

impl OcrGrounder {
    pub async fn extract_elements(image_path: &str) -> Result<Vec<UIElement>> {
        let output = Command::new("tesseract")
            .args([image_path, "stdout", "tsv"])
            .output()
            .await
            .context("Failed to run tesseract CLI")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("Tesseract OCR failed: {}", stderr);
        }

        let text = String::from_utf8_lossy(&output.stdout);
        let mut elements = Vec::new();
        let mut counter = 1;

        // Track lines for line-level grouping
        let mut current_line_key = String::new();
        let mut line_words: Vec<String> = Vec::new();
        let mut line_box: Option<(i32, i32, i32, i32)> = None;

        for line in text.lines().skip(1) {
            let parts: Vec<&str> = line.split('\t').collect();
            if parts.len() < 12 || parts[0] != "5" {
                continue;
            }

            let word = parts[11].trim();
            if word.is_empty() {
                continue;
            }

            let conf_str = parts[10];
            let conf: f64 = conf_str.parse().unwrap_or(-1.0);
            if conf < 25.0 {
                continue;
            }

            let x: i32 = parts[6].parse().unwrap_or(0);
            let y: i32 = parts[7].parse().unwrap_or(0);
            let width: u32 = parts[8].parse().unwrap_or(0);
            let height: u32 = parts[9].parse().unwrap_or(0);

            if width == 0 || height == 0 {
                continue;
            }

            let block_num = parts[2];
            let par_num = parts[3];
            let line_num = parts[4];
            let line_key = format!("{}_{}_{}", block_num, par_num, line_num);

            if line_key != current_line_key {
                // Flush previous line phrase if multi-word
                if line_words.len() > 1 {
                    if let Some((lx, ly, lw, lh)) = line_box {
                        elements.push(UIElement {
                            ref_id: format!("@e{}", counter),
                            text: line_words.join(" "),
                            x: lx,
                            y: ly,
                            width: lw as u32,
                            height: lh as u32,
                            confidence: Some(0.95),
                            role: Some("phrase".to_string()),
                        });
                        counter += 1;
                    }
                }
                current_line_key = line_key;
                line_words.clear();
                line_box = Some((x, y, width as i32, height as i32));
            } else if let Some((lx, ly, lw, lh)) = line_box {
                let right = (x + width as i32).max(lx + lw);
                let bottom = (y + height as i32).max(ly + lh);
                let min_x = lx.min(x);
                let min_y = ly.min(y);
                line_box = Some((min_x, min_y, right - min_x, bottom - min_y));
            }

            line_words.push(word.to_string());

            // Add single word element
            elements.push(UIElement {
                ref_id: format!("@e{}", counter),
                text: word.to_string(),
                x,
                y,
                width,
                height,
                confidence: Some(conf / 100.0),
                role: Some("text".to_string()),
            });

            counter += 1;
        }

        // Flush final line phrase if multi-word
        if line_words.len() > 1 {
            if let Some((lx, ly, lw, lh)) = line_box {
                elements.push(UIElement {
                    ref_id: format!("@e{}", counter),
                    text: line_words.join(" "),
                    x: lx,
                    y: ly,
                    width: lw as u32,
                    height: lh as u32,
                    confidence: Some(0.95),
                    role: Some("phrase".to_string()),
                });
            }
        }

        debug!("Extracted {} OCR elements from {}", elements.len(), image_path);
        Ok(elements)
    }
}
