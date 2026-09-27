sahil:    
    telling ai open <something>
    opens the window search bar and types that thing
    it should first see the screen

    i think it does not detect desktop (i.e no app open) (it only detects app)

KhannaSparsh0001:
    even after repeated trials, the agent aint working. It suggest the actions but does not perform it actually...!


|||

$ docker compose -f common/docker-compose.yml up -d && bun run tauri:dev
[+] up 1/1
 ✔ Container blinky-searxng Running                                                                                 0.0s
$ bun tauri dev
     Running BeforeDevCommand (`vite --config common/frontend/vite.config.ts`)

  VITE v8.0.14  ready in 568 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
     Running DevCommand (`cargo  run --no-default-features --color always --`)
        Info Watching C:\Users\khann\Projects\Blinky\common\src-tauri for changes...
warning: function `start_ydotoold` is never used
   --> src\lib.rs:638:4
    |
638 | fn start_ydotoold() {
    |    ^^^^^^^^^^^^^^
    |
    = note: `#[warn(dead_code)]` (part of `#[warn(unused)]`) on by default

warning: function `start_mcp_bridge` is never used
 --> src\mcp_bridge.rs:7:8
  |
7 | pub fn start_mcp_bridge() {
  |        ^^^^^^^^^^^^^^^^

warning: function `handle_client` is never used
  --> src\mcp_bridge.rs:49:10
   |
49 | async fn handle_client(stream: TcpStream) {
   |          ^^^^^^^^^^^^^

warning: function `find_mcp_binary` is never used
   --> src\mcp_bridge.rs:126:4
    |
126 | fn find_mcp_binary() -> String {
    |    ^^^^^^^^^^^^^^^

warning: function `dirs_runtime_dir` is never used
   --> src\mcp_bridge.rs:139:4
    |
139 | fn dirs_runtime_dir() -> std::path::PathBuf {
    |    ^^^^^^^^^^^^^^^^


|||
    

    sahil:
        make sure to do docker compose because it require searxng