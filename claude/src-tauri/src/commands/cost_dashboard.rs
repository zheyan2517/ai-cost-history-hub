//! Local cost dashboard process manager.
//!
//! Spawns / reuses the pure-Python cost service bound only to 127.0.0.1
//! and opens it in the system browser.

use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::State;

const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8753;
const PORT_SCAN_RANGE: u16 = 20;
const READY_TIMEOUT: Duration = Duration::from_secs(15);
const READY_POLL: Duration = Duration::from_millis(200);

/// Shared handle for the running cost dashboard process.
#[derive(Default)]
pub struct CostDashboardState {
    inner: Mutex<SidecarState>,
}

#[derive(Default)]
struct SidecarState {
    child: Option<Child>,
    port: Option<u16>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CostDashboardStatus {
    pub running: bool,
    pub url: Option<String>,
    pub port: Option<u16>,
    pub pid: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CostDashboardOpenResult {
    pub url: String,
    pub port: u16,
    pub started: bool,
}

fn url_for(port: u16) -> String {
    format!("http://{DEFAULT_HOST}:{port}")
}

fn resolve_agent_dir() -> Result<PathBuf, String> {
    if let Ok(env_dir) = std::env::var("AGENT_COST_DASHBOARD_DIR") {
        let path = PathBuf::from(env_dir);
        if path.join("cost_dashboard.py").is_file() {
            return Ok(canonicalize_soft(&path));
        }
        return Err(format!(
            "AGENT_COST_DASHBOARD_DIR is set but cost_dashboard.py was not found in: {}",
            path.display()
        ));
    }

    let mut candidates: Vec<PathBuf> = Vec::new();

    // Dev layout: wangquanti/claude/src-tauri -> wangquanti/agent
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("agent"),
    );
    // agent next to claude project root
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("agent"),
    );

    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("agent"));
            candidates.push(exe_dir.join("..").join("agent"));
            candidates.push(exe_dir.join("resources").join("agent"));
            candidates.push(exe_dir.join("..").join("..").join("agent"));
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("agent"));
        candidates.push(cwd.join("..").join("agent"));
        candidates.push(cwd.join("wangquanti").join("agent"));
    }

    for candidate in candidates {
        if candidate.join("cost_dashboard.py").is_file() {
            return Ok(canonicalize_soft(&candidate));
        }
    }

    Err(
        "Could not locate cost_dashboard.py. \
         Set AGENT_COST_DASHBOARD_DIR or keep agent/ beside claude/."
            .to_string(),
    )
}

fn canonicalize_soft(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn find_python() -> Result<(PathBuf, Vec<String>), String> {
    #[cfg(windows)]
    {
        if let Ok(output) = Command::new("py").args(["-3", "--version"]).output() {
            if output.status.success() {
                return Ok((PathBuf::from("py"), vec!["-3".to_string()]));
            }
        }
    }

    for candidate in ["python", "python3"] {
        if let Ok(output) = Command::new(candidate).arg("--version").output() {
            if output.status.success() {
                return Ok((PathBuf::from(candidate), Vec::new()));
            }
        }
    }

    Err(
        "Python 3.12+ not found. Install Python and ensure `python` or `py -3` is on PATH."
            .to_string(),
    )
}

fn tcp_open(port: u16) -> bool {
    TcpStream::connect_timeout(
        &format!("{DEFAULT_HOST}:{port}").parse().unwrap(),
        Duration::from_millis(120),
    )
    .is_ok()
}

/// Lightweight HTTP GET / — confirms a web server is responding.
fn http_ready(port: u16) -> bool {
    let addr = format!("{DEFAULT_HOST}:{port}");
    let Ok(mut stream) =
        TcpStream::connect_timeout(&addr.parse().unwrap(), Duration::from_millis(300))
    else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let req = format!(
        "GET / HTTP/1.1\r\nHost: {DEFAULT_HOST}:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    match stream.read(&mut buf) {
        Ok(n) if n > 0 => {
            let head = String::from_utf8_lossy(&buf[..n]);
            head.starts_with("HTTP/1.")
        }
        _ => false,
    }
}

fn is_port_free(port: u16) -> bool {
    !tcp_open(port)
}

fn pick_port() -> Result<u16, String> {
    for offset in 0..PORT_SCAN_RANGE {
        let port = DEFAULT_PORT + offset;
        if is_port_free(port) {
            return Ok(port);
        }
    }
    Err(format!(
        "No free port found in range {DEFAULT_PORT}-{}",
        DEFAULT_PORT + PORT_SCAN_RANGE - 1
    ))
}

fn wait_until_ready(port: u16) -> bool {
    let deadline = Instant::now() + READY_TIMEOUT;
    while Instant::now() < deadline {
        if http_ready(port) {
            return true;
        }
        thread::sleep(READY_POLL);
    }
    false
}

fn open_browser(url: &str) -> Result<(), String> {
    tauri_plugin_opener::open_url(url, None::<String>)
        .map_err(|e| format!("Failed to open browser: {e}"))
}

fn spawn_dashboard(agent_dir: &Path, port: u16) -> Result<(Child, PathBuf), String> {
    let script = agent_dir.join("cost_dashboard.py");
    if !script.is_file() {
        return Err(format!("Missing script: {}", script.display()));
    }

    let (python, prefix_args) = find_python()?;
    let mut args = prefix_args;
    args.push(script.to_string_lossy().to_string());
    // Security: always bind loopback only.
    args.push("--host".to_string());
    args.push(DEFAULT_HOST.to_string());
    args.push("--port".to_string());
    args.push(port.to_string());

    let log_path = std::env::temp_dir().join(format!("wangquanti-cost-dashboard-{port}.log"));
    let log_file = fs::File::create(&log_path)
        .map_err(|e| format!("Cannot create sidecar log {}: {e}", log_path.display()))?;
    let log_err = log_file
        .try_clone()
        .map_err(|e| format!("Cannot clone log handle: {e}"))?;

    let mut cmd = Command::new(&python);
    cmd.args(&args)
        .current_dir(agent_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log_file))
        .stderr(Stdio::from(log_err));

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd.spawn().map_err(|e| {
        format!(
            "Failed to start cost dashboard with {}: {e}",
            python.display()
        )
    })?;
    Ok((child, log_path))
}

fn kill_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

fn child_still_running(child: &mut Child) -> bool {
    matches!(child.try_wait(), Ok(None))
}

fn take_dead_child(state: &mut SidecarState) {
    if let Some(child) = state.child.as_mut() {
        if !child_still_running(child) {
            state.child = None;
            state.port = None;
        }
    }
}

/// Start the local cost service if needed and open it in the system browser.
#[tauri::command]
pub async fn open_cost_dashboard(
    state: State<'_, CostDashboardState>,
) -> Result<CostDashboardOpenResult, String> {
    // Phase 1: check managed process without holding lock across network waits.
    {
        let mut guard = state
            .inner
            .lock()
            .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;
        take_dead_child(&mut guard);
        let port = guard.port;
        let alive = guard
            .child
            .as_mut()
            .is_some_and(child_still_running);
        if let Some(port) = port {
            if alive && http_ready(port) {
                let url = url_for(port);
                drop(guard);
                open_browser(&url)?;
                return Ok(CostDashboardOpenResult {
                    url,
                    port,
                    started: false,
                });
            }
        }
    }

    // Phase 2: reuse an external dashboard already on the default port
    // (e.g. started by start.bat / coordinator).
    if http_ready(DEFAULT_PORT) {
        let url = url_for(DEFAULT_PORT);
        open_browser(&url)?;
        return Ok(CostDashboardOpenResult {
            url,
            port: DEFAULT_PORT,
            started: false,
        });
    }

    // Phase 3: spawn a new sidecar.
    let agent_dir = resolve_agent_dir()?;
    let port = pick_port()?;
    let (mut child, log_path) = spawn_dashboard(&agent_dir, port)?;

    if !wait_until_ready(port) {
        kill_child(&mut child);
        let tail = fs::read_to_string(&log_path).unwrap_or_default();
        let tail = tail.chars().rev().take(1200).collect::<String>();
        let tail: String = tail.chars().rev().collect();
        return Err(format!(
            "Cost dashboard did not become ready on {DEFAULT_HOST}:{port} within {}s.\nLog:\n{tail}",
            READY_TIMEOUT.as_secs()
        ));
    }

    let url = url_for(port);
    open_browser(&url)?;

    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;
    // If something else was stored meanwhile, replace after killing old.
    if let Some(mut old) = guard.child.take() {
        kill_child(&mut old);
    }
    guard.child = Some(child);
    guard.port = Some(port);

    Ok(CostDashboardOpenResult {
        url,
        port,
        started: true,
    })
}

/// Stop the managed cost service process if it is running.
#[tauri::command]
pub async fn stop_cost_dashboard(
    state: State<'_, CostDashboardState>,
) -> Result<bool, String> {
    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;

    if let Some(mut child) = guard.child.take() {
        kill_child(&mut child);
        guard.port = None;
        return Ok(true);
    }
    Ok(false)
}

/// Query whether a managed cost service is currently running.
#[tauri::command]
pub async fn cost_dashboard_status(
    state: State<'_, CostDashboardState>,
) -> Result<CostDashboardStatus, String> {
    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;

    take_dead_child(&mut guard);

    let port = guard.port;
    let pid = guard.child.as_ref().map(Child::id);
    if let (Some(port), Some(pid)) = (port, pid) {
        return Ok(CostDashboardStatus {
            running: true,
            url: Some(url_for(port)),
            port: Some(port),
            pid: Some(pid),
        });
    }

    // Report external instance if present.
    if http_ready(DEFAULT_PORT) {
        return Ok(CostDashboardStatus {
            running: true,
            url: Some(url_for(DEFAULT_PORT)),
            port: Some(DEFAULT_PORT),
            pid: None,
        });
    }

    Ok(CostDashboardStatus {
        running: false,
        url: None,
        port: None,
        pid: None,
    })
}

/// Kill the managed cost service on app exit (best-effort).
pub fn shutdown_cost_dashboard(state: &CostDashboardState) {
    if let Ok(mut guard) = state.inner.lock() {
        if let Some(mut child) = guard.child.take() {
            kill_child(&mut child);
        }
        guard.port = None;
    }
}
