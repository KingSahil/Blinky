use crate::protocol::models::{
    AnchoredTarget, CaptureKind, FrameDescriptor, MonitorInfo, UIElement, WindowBounds, WindowInfo,
};
use anyhow::{bail, Result};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[derive(Debug, Clone, Default)]
pub struct FrameStore {
    frames: Arc<RwLock<HashMap<String, FrameDescriptor>>>,
}

impl FrameStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&self, frame: FrameDescriptor) {
        let mut lock = self.frames.write().unwrap();
        // Keep max 50 frames in memory
        if lock.len() > 50 {
            let oldest_key = lock
                .iter()
                .min_by_key(|(_, f)| f.timestamp_ms)
                .map(|(k, _)| k.clone());
            if let Some(k) = oldest_key {
                lock.remove(&k);
            }
        }
        lock.insert(frame.frame_id.clone(), frame);
    }

    pub fn get(&self, frame_id: &str) -> Option<FrameDescriptor> {
        let lock = self.frames.read().unwrap();
        lock.get(frame_id).cloned()
    }

    pub fn attach_elements(&self, frame_id: &str, elements: Vec<UIElement>) -> Result<()> {
        let mut lock = self.frames.write().unwrap();
        if let Some(frame) = lock.get_mut(frame_id) {
            frame.elements = elements;
            Ok(())
        } else {
            bail!("Frame '{}' not found in frame store", frame_id);
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct CoordinateEngine;

impl CoordinateEngine {
    /// Calculate the logical (dx, dy) offset of a click target relative to a window's top-left corner.
    pub fn compute_relative_offset(
        click_x: i32,
        click_y: i32,
        is_crop: bool,
        captured_bounds: &WindowBounds,
        scale: f64,
    ) -> (i32, i32) {
        let safe_scale = if scale <= 0.0 { 1.0 } else { scale };

        if is_crop {
            let dx = (click_x as f64 / safe_scale).round() as i32;
            let dy = (click_y as f64 / safe_scale).round() as i32;
            (dx, dy)
        } else {
            let logical_x = (click_x as f64 / safe_scale).round() as i32;
            let logical_y = (click_y as f64 / safe_scale).round() as i32;
            let dx = logical_x - captured_bounds.x;
            let dy = logical_y - captured_bounds.y;
            (dx, dy)
        }
    }

    /// Re-anchor a relative (dx, dy) offset to a window's live bounding box with strict inset clamping.
    pub fn resolve_target(
        window_address: &str,
        dx: i32,
        dy: i32,
        live_bounds: &WindowBounds,
    ) -> Result<AnchoredTarget> {
        let unconstrained_x = live_bounds.x + dx;
        let unconstrained_y = live_bounds.y + dy;

        // Safeguard 1: Strict Window Inset Clamping (prevent cursor from escaping window borders)
        let safe_inset = 2;
        let min_x = live_bounds.x + safe_inset;
        let max_x = live_bounds.x + (live_bounds.width as i32 - safe_inset).max(safe_inset);
        let min_y = live_bounds.y + safe_inset;
        let max_y = live_bounds.y + (live_bounds.height as i32 - safe_inset).max(safe_inset);

        let target_x = unconstrained_x.clamp(min_x, max_x);
        let target_y = unconstrained_y.clamp(min_y, max_y);

        Ok(AnchoredTarget {
            target_x,
            target_y,
            window_address: Some(window_address.to_string()),
            relative_dx: dx,
            relative_dy: dy,
            current_bounds: Some(*live_bounds),
        })
    }

    /// High-level frame resolution: maps a target reference (@e3), semantic text,
    /// or point on a frame descriptor (pixel or normalized) to live screen coordinates,
    /// automatically re-anchoring if the target window moved and enforcing resize/clamp safeguards.
    pub fn resolve_frame_target(
        frame: &FrameDescriptor,
        target_raw: Option<(f64, f64)>,
        target_ref: Option<&str>,
        target_text: Option<&str>,
        force_normalized: Option<bool>,
        live_windows: &[WindowInfo],
        _monitors: &[MonitorInfo],
    ) -> Result<AnchoredTarget> {
        // 1. Resolve element from ref or text if given
        let matched_element: Option<&UIElement> = if let Some(r) = target_ref {
            frame
                .elements
                .iter()
                .find(|e| e.ref_id.eq_ignore_ascii_case(r))
        } else if let Some(t) = target_text {
            let t_lower = t.trim().to_lowercase();
            frame
                .elements
                .iter()
                .find(|e| e.text.to_lowercase().contains(&t_lower))
        } else {
            None
        };

        if let Some(elem) = matched_element {
            let (elem_cx, elem_cy) = elem.center();
            return Self::resolve_frame_target(
                frame,
                Some((elem_cx as f64, elem_cy as f64)),
                None,
                None,
                Some(false), // exact pixel coordinates inside the image
                live_windows,
                _monitors,
            );
        }

        if target_ref.is_some() {
            bail!(
                "Target ref '{}' not found in frame '{}' (available elements: {})",
                target_ref.unwrap(),
                frame.frame_id,
                frame.elements.len()
            );
        }

        if target_text.is_some() {
            bail!(
                "Target text '{}' not found in frame '{}' (available elements: {})",
                target_text.unwrap(),
                frame.frame_id,
                frame.elements.len()
            );
        }

        let (raw_x, raw_y) = target_raw.ok_or_else(|| {
            anyhow::anyhow!("Must provide either 'ref', 'text', or 'target' [x, y] coordinates")
        })?;

        // Determine if coordinates are normalized [0.0..1.0] or image pixel coordinates
        let is_norm = match force_normalized {
            Some(n) => n,
            None => raw_x >= 0.0 && raw_x <= 1.0 && raw_y >= 0.0 && raw_y <= 1.0,
        };

        let (norm_u, norm_v) = if is_norm {
            (raw_x, raw_y)
        } else {
            (
                (raw_x / frame.image_width as f64).clamp(0.0, 1.0),
                (raw_y / frame.image_height as f64).clamp(0.0, 1.0),
            )
        };

        match frame.capture_kind {
            CaptureKind::Window => {
                let addr = frame.window_address.as_deref().unwrap_or("");
                if addr.is_empty() {
                    bail!("Window frame descriptor missing window_address");
                }

                // Find live window
                let live_win = live_windows.iter().find(|w| w.address == addr);
                if let Some(win) = live_win {
                    // Safeguard 2: Resize Drift Safety Gate (>35% dimension change requires re-observation)
                    let width_ratio = win.bounds.width as f64 / frame.source_bounds.width as f64;
                    let height_ratio =
                        win.bounds.height as f64 / frame.source_bounds.height as f64;
                    if (width_ratio - 1.0).abs() > 0.35 || (height_ratio - 1.0).abs() > 0.35 {
                        bail!(
                            "Window '{}' resized significantly (>35%) between observation and action (orig: {}x{}, live: {}x{}); re-observation required",
                            addr,
                            frame.source_bounds.width,
                            frame.source_bounds.height,
                            win.bounds.width,
                            win.bounds.height
                        );
                    }

                    // Relative offset within the window's original logical bounds
                    let dx = (norm_u * win.bounds.width as f64).round() as i32;
                    let dy = (norm_v * win.bounds.height as f64).round() as i32;

                    // Safeguard 1: Window Inset Clamping
                    let safe_inset = 2;
                    let min_x = win.bounds.x + safe_inset;
                    let max_x =
                        win.bounds.x + (win.bounds.width as i32 - safe_inset).max(safe_inset);
                    let min_y = win.bounds.y + safe_inset;
                    let max_y =
                        win.bounds.y + (win.bounds.height as i32 - safe_inset).max(safe_inset);

                    let target_x = (win.bounds.x + dx).clamp(min_x, max_x);
                    let target_y = (win.bounds.y + dy).clamp(min_y, max_y);

                    Ok(AnchoredTarget {
                        target_x,
                        target_y,
                        window_address: Some(addr.to_string()),
                        relative_dx: dx,
                        relative_dy: dy,
                        current_bounds: Some(win.bounds),
                    })
                } else {
                    bail!(
                        "Target window '{}' was closed or unmapped between observation and action",
                        addr
                    );
                }
            }
            CaptureKind::Fullscreen | CaptureKind::Region => {
                // Logical point on the observed screen
                let orig_logical_x = frame.source_bounds.x
                    + (norm_u * frame.source_bounds.width as f64).round() as i32;
                let orig_logical_y = frame.source_bounds.y
                    + (norm_v * frame.source_bounds.height as f64).round() as i32;

                // Hit-test if this point fell inside a specific window at capture time
                let hit_win = live_windows.iter().find(|w| {
                    if let Some(addr) = &frame.window_address {
                        w.address == *addr
                    } else {
                        w.bounds.contains_point(orig_logical_x, orig_logical_y)
                    }
                });

                if let Some(win) = hit_win {
                    // Window re-anchoring: preserve the offset inside this window
                    let dx = orig_logical_x - frame.source_bounds.x;
                    let dy = orig_logical_y - frame.source_bounds.y;

                    let safe_inset = 2;
                    let min_x = win.bounds.x + safe_inset;
                    let max_x =
                        win.bounds.x + (win.bounds.width as i32 - safe_inset).max(safe_inset);
                    let min_y = win.bounds.y + safe_inset;
                    let max_y =
                        win.bounds.y + (win.bounds.height as i32 - safe_inset).max(safe_inset);

                    let target_x = (win.bounds.x + dx).clamp(min_x, max_x);
                    let target_y = (win.bounds.y + dy).clamp(min_y, max_y);

                    Ok(AnchoredTarget {
                        target_x,
                        target_y,
                        window_address: Some(win.address.clone()),
                        relative_dx: dx,
                        relative_dy: dy,
                        current_bounds: Some(win.bounds),
                    })
                } else {
                    // Background / desktop bar click
                    Ok(AnchoredTarget {
                        target_x: orig_logical_x,
                        target_y: orig_logical_y,
                        window_address: None,
                        relative_dx: 0,
                        relative_dy: 0,
                        current_bounds: None,
                    })
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_relative_offset_crop_scale_1() {
        let bounds = WindowBounds {
            x: 100,
            y: 200,
            width: 800,
            height: 600,
        };
        let (dx, dy) = CoordinateEngine::compute_relative_offset(250, 150, true, &bounds, 1.0);
        assert_eq!(dx, 250);
        assert_eq!(dy, 150);
    }

    #[test]
    fn test_element_ref_targeting() {
        let frame = FrameDescriptor {
            frame_id: "frm_test_ref".to_string(),
            capture_kind: CaptureKind::Window,
            window_address: Some("0x1234".to_string()),
            source_bounds: WindowBounds {
                x: 100,
                y: 100,
                width: 1000,
                height: 800,
            },
            image_width: 1000,
            image_height: 800,
            scale: 1.0,
            monitor_id: 0,
            timestamp_ms: 1000,
            elements: vec![UIElement {
                ref_id: "@e3".to_string(),
                text: "Artifacts".to_string(),
                x: 400,
                y: 300,
                width: 100,
                height: 40,
                confidence: Some(0.95),
                role: Some("button".to_string()),
            }],
        };

        let live_windows = vec![WindowInfo {
            address: "0x1234".to_string(),
            title: "Hermes".to_string(),
            class: "hermes".to_string(),
            initial_class: "hermes".to_string(),
            pid: Some(100),
            bounds: WindowBounds {
                x: 200,
                y: 150,
                width: 1000,
                height: 800,
            },
            monitor_id: 0,
            workspace_id: 1,
            focused: true,
            floating: true,
            fullscreen: false,
        }];

        // Resolve by ref "@e3"
        let target = CoordinateEngine::resolve_frame_target(
            &frame,
            None,
            Some("@e3"),
            None,
            None,
            &live_windows,
            &[],
        )
        .unwrap();

        // Element center is 400 + 50 = 450, 300 + 20 = 320
        // Live target is 200 + 450 = 650, 150 + 320 = 470
        assert_eq!(target.target_x, 650);
        assert_eq!(target.target_y, 470);
        assert_eq!(target.relative_dx, 450);
        assert_eq!(target.relative_dy, 320);
    }

    #[test]
    fn test_resize_drift_safety_gate_rejection() {
        let frame = FrameDescriptor {
            frame_id: "frm_test_drift".to_string(),
            capture_kind: CaptureKind::Window,
            window_address: Some("0x1234".to_string()),
            source_bounds: WindowBounds {
                x: 100,
                y: 100,
                width: 1000,
                height: 800,
            },
            image_width: 1000,
            image_height: 800,
            scale: 1.0,
            monitor_id: 0,
            timestamp_ms: 1000,
            elements: vec![],
        };

        // Window doubled in width (1000 -> 2000)
        let live_windows = vec![WindowInfo {
            address: "0x1234".to_string(),
            title: "Hermes".to_string(),
            class: "hermes".to_string(),
            initial_class: "hermes".to_string(),
            pid: Some(100),
            bounds: WindowBounds {
                x: 100,
                y: 100,
                width: 2000,
                height: 800,
            },
            monitor_id: 0,
            workspace_id: 1,
            focused: true,
            floating: true,
            fullscreen: false,
        }];

        let result = CoordinateEngine::resolve_frame_target(
            &frame,
            Some((0.5, 0.5)),
            None,
            None,
            Some(true),
            &live_windows,
            &[],
        );

        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(err_msg.contains("resized significantly"));
    }

    #[test]
    fn test_window_inset_clamping() {
        let frame = FrameDescriptor {
            frame_id: "frm_test_clamp".to_string(),
            capture_kind: CaptureKind::Window,
            window_address: Some("0x1234".to_string()),
            source_bounds: WindowBounds {
                x: 100,
                y: 100,
                width: 500,
                height: 400,
            },
            image_width: 500,
            image_height: 400,
            scale: 1.0,
            monitor_id: 0,
            timestamp_ms: 1000,
            elements: vec![],
        };

        let live_windows = vec![WindowInfo {
            address: "0x1234".to_string(),
            title: "Hermes".to_string(),
            class: "hermes".to_string(),
            initial_class: "hermes".to_string(),
            pid: Some(100),
            bounds: WindowBounds {
                x: 100,
                y: 100,
                width: 500,
                height: 400,
            },
            monitor_id: 0,
            workspace_id: 1,
            focused: true,
            floating: true,
            fullscreen: false,
        }];

        // Point at [1.0, 1.0] bottom-right corner
        let target = CoordinateEngine::resolve_frame_target(
            &frame,
            Some((1.0, 1.0)),
            None,
            None,
            Some(true),
            &live_windows,
            &[],
        )
        .unwrap();

        // Clamped inside window: x <= 100 + 500 - 2 = 598, y <= 100 + 400 - 2 = 498
        assert_eq!(target.target_x, 598);
        assert_eq!(target.target_y, 498);
    }
}
