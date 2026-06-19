fn main() {
    #[cfg(not(target_os = "windows"))]
    {
        std::env::set_var("GDK_BACKEND", "x11");
        std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
    }

    blinky_lib::run()
}
