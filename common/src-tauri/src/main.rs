struct CursorGuard;

impl Drop for CursorGuard {
    fn drop(&mut self) {
        #[cfg(target_os = "windows")]
        unsafe {
            use windows_sys::Win32::UI::WindowsAndMessaging::{SystemParametersInfoW, SPI_SETCURSORS};
            SystemParametersInfoW(SPI_SETCURSORS, 0, std::ptr::null_mut(), 0);
        }
    }
}

fn main() {
    let _guard = CursorGuard;

    #[cfg(not(target_os = "windows"))]
    {
        std::env::set_var("GDK_BACKEND", "x11");
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
    }

    blinky_lib::run()
}

