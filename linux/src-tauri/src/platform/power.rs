use std::process::Command;

pub fn execute_power_off() {
    if let Err(e) = Command::new("systemctl").arg("poweroff").spawn() {
        eprintln!("Failed to execute Linux/Unix poweroff: {:?}", e);
    }
}

pub fn execute_restart() {
    if let Err(e) = Command::new("systemctl").arg("reboot").spawn() {
        eprintln!("Failed to execute Linux/Unix reboot: {:?}", e);
    }
}

pub fn execute_sleep() {
    if let Err(e) = Command::new("systemctl").arg("suspend").spawn() {
        eprintln!("Failed to execute Linux/Unix suspend: {:?}", e);
    }
}
