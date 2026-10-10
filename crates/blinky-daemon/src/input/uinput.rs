use anyhow::{bail, Context, Result};
use evdev::uinput::{VirtualDevice, VirtualDeviceBuilder};
use evdev::{AttributeSet, InputEvent, Key, RelativeAxisType};
use std::thread::sleep;
use std::time::Duration;
use tracing::{debug, warn};

pub struct VirtualMouse {
    device: Option<VirtualDevice>,
}

impl VirtualMouse {
    pub fn new() -> Result<Self> {
        match Self::create_virtual_device() {
            Ok(device) => {
                debug!("Created virtual uinput mouse device successfully");
                Ok(Self {
                    device: Some(device),
                })
            }
            Err(e) => {
                warn!(
                    "Could not create direct /dev/uinput device ({}); falling back to ydotool",
                    e
                );
                Ok(Self { device: None })
            }
        }
    }

    fn create_virtual_device() -> Result<VirtualDevice> {
        let mut keys = AttributeSet::<Key>::new();
        keys.insert(Key::BTN_LEFT);
        keys.insert(Key::BTN_RIGHT);
        keys.insert(Key::BTN_MIDDLE);

        let mut rel_axes = AttributeSet::<RelativeAxisType>::new();
        rel_axes.insert(RelativeAxisType::REL_X);
        rel_axes.insert(RelativeAxisType::REL_Y);
        rel_axes.insert(RelativeAxisType::REL_WHEEL);
        rel_axes.insert(RelativeAxisType::REL_HWHEEL);

        let device = VirtualDeviceBuilder::new()?
            .name("Blinky Virtual Mouse")
            .with_keys(&keys)?
            .with_relative_axes(&rel_axes)?
            .build()
            .context("Failed to build virtual uinput device")?;

        Ok(device)
    }

    pub fn click(&mut self, button: &str, count: u32) -> Result<()> {
        let key = match button.to_lowercase().as_str() {
            "left" => Key::BTN_LEFT,
            "right" => Key::BTN_RIGHT,
            "middle" => Key::BTN_MIDDLE,
            other => bail!("Unknown mouse button: {}", other),
        };

        let click_count = count.max(1);

        if let Some(dev) = &mut self.device {
            for _ in 0..click_count {
                // Press down
                let down = InputEvent::new(evdev::EventType::KEY, key.code(), 1);
                dev.emit(&[down])
                    .context("Failed to emit mouse button down")?;
                sleep(Duration::from_millis(30));

                // Release up
                let up = InputEvent::new(evdev::EventType::KEY, key.code(), 0);
                dev.emit(&[up]).context("Failed to emit mouse button up")?;
                sleep(Duration::from_millis(30));
            }
            Ok(())
        } else {
            // ydotool fallback
            let hex_code = match button.to_lowercase().as_str() {
                "right" => "0xC1",
                "middle" => "0xC2",
                _ => "0xC0",
            };
            for _ in 0..click_count {
                let status = std::process::Command::new("ydotool")
                    .args(["click", hex_code])
                    .status()
                    .context("Failed to spawn ydotool click")?;
                if !status.success() {
                    bail!("ydotool click failed with status: {:?}", status);
                }
                sleep(Duration::from_millis(30));
            }
            Ok(())
        }
    }

    pub fn scroll(&mut self, dx: i32, dy: i32) -> Result<()> {
        if let Some(dev) = &mut self.device {
            let mut events = Vec::new();
            if dy != 0 {
                events.push(InputEvent::new(
                    evdev::EventType::RELATIVE,
                    RelativeAxisType::REL_WHEEL.0,
                    dy,
                ));
            }
            if dx != 0 {
                events.push(InputEvent::new(
                    evdev::EventType::RELATIVE,
                    RelativeAxisType::REL_HWHEEL.0,
                    dx,
                ));
            }
            if !events.is_empty() {
                dev.emit(&events).context("Failed to emit scroll events")?;
            }
            Ok(())
        } else {
            // ydotool fallback: ydotool mousemove -w -- dx dy
            let status = std::process::Command::new("ydotool")
                .args(["mousemove", "-w", "--", &dx.to_string(), &dy.to_string()])
                .status()
                .context("Failed to spawn ydotool mousemove scroll")?;
            if !status.success() {
                bail!("ydotool scroll failed with status: {:?}", status);
            }
            Ok(())
        }
    }
}
