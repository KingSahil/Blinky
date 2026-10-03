fn main() {
    println!("cargo:rerun-if-env-changed=BLINKY_TRANSPORT_MODE");
    println!("cargo:rerun-if-changed=icons/icon.ico");
    println!("cargo:rerun-if-changed=icons/icon.png");
    println!("cargo:rerun-if-changed=tauri.conf.json");
    let mode = std::env::var("BLINKY_TRANSPORT_MODE").unwrap_or_else(|_| "development".to_string());
    assert!(
        matches!(
            mode.trim().to_ascii_lowercase().as_str(),
            "" | "dev" | "development" | "release"
        ),
        "Unsupported BLINKY_TRANSPORT_MODE: {mode}. Use development or release."
    );
    println!("cargo:rustc-env=BLINKY_TRANSPORT_MODE={mode}");
    tauri_build::build()
}
