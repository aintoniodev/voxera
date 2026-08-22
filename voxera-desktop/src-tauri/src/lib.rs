// voxera desktop shell (Track 7): the CLI generates everything; this window
// wraps the thin UI (ui/server.py) as a sidecar process.
use std::net::TcpStream;
use std::process::{Child, Command};
use std::thread;
use std::time::{Duration, Instant};

use tauri::WebviewUrl;

const UI_ADDR: &str = "127.0.0.1:8770";
const UI_URL: &str = "http://127.0.0.1:8770";

fn server_up() -> bool {
    TcpStream::connect(UI_ADDR).is_ok()
}

fn project_root() -> std::path::PathBuf {
    // build-time manifest dir: <repo>/voxera-desktop/src-tauri
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn spawn_server() -> Option<Child> {
    if server_up() {
        return None; // already running (e.g. started manually)
    }
    let root = project_root();
    let py = root.join(".venv-ims/Scripts/python.exe");
    let mut args = vec![root.join("ui/server.py").to_string_lossy().into_owned(), "8770".into()];
    // venv python first (product env), then any python on PATH
    let mut cmds: Vec<Command> = Vec::new();
    let mut c1 = Command::new(&py);
    c1.args(&args).current_dir(&root);
    cmds.push(c1);
    let mut c2 = Command::new("python");
    c2.args(&args).current_dir(&root);
    cmds.push(c2);
    for mut cmd in cmds {
        if let Ok(child) = cmd.spawn() {
            return Some(child);
        }
    }
    None
}

fn wait_for_server(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if server_up() {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut server = spawn_server();
    let app = tauri::Builder::default()
        .setup(|app| {
            if !wait_for_server(Duration::from_secs(10)) {
                eprintln!("voxera UI server did not start on {UI_ADDR}");
            }
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(UI_URL.parse().unwrap()),
            )
            .title("voxera — Sound like you, only better")
            .inner_size(1100.0, 750.0)
            .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    app.run(move |_handle, event| {
        match event {
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                if let Some(child) = server.as_mut() {
                    let pid = child.id().to_string();
                    // kill the process tree (python + any children) by PID
                    let _ = Command::new("taskkill")
                        .args(["/PID", &pid, "/T", "/F"])
                        .spawn();
                }
            }
            _ => {}
        }
    });
}
