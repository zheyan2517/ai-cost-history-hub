//! Agent Cost Dashboard sidecar.
//!
//! Spawns the pure-Python cost dashboard as a local subprocess bound only to
//! 127.0.0.1, and opens it in the system browser via the opener plugin.

use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::State;

const DEFAULT_PORT: u16 = 8753;
const PORT_SCAN_RANGE: u16 = 20;
const READY_TIMEOUT: Duration = Duration::from_secs(15);
const READY_POLL: Duration = Duration::from_millis(200);

/// Shared handle for the running cost-dashboard process.
#[derive(Default)]
pub struct CostDashboardState {
    inner: Mutex<Option<RunningDashboard>>,
}

struct RunningDashboard {
    child: Child,
    port: u16,
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

fn resolve_agent_dir() -> Result<PathBuf, String> {
    if let Ok(env_dir) = std::env::var("AGENT_COST_DASHBOARD_DIR") {
        let path = PathBuf::from(env_dir);
        if path.join("cost_dashboard.py").is_file() {
            return Ok(path);
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
    // Alternate: agent next to claude project root
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
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("agent"));
        candidates.push(cwd.join("..").join("agent"));
    }

    for candidate in candidates {
        if let Ok(canonical) = candidate.canonicalize() {
            if canonical.join("cost_dashboard.py").is_file() {
                return Ok(canonical);
            }
        } else if candidate.join("cost_dashboard.py").is_file() {
            return Ok(candidate);
        }
    }

    Err(
        "Could not locate agent cost dashboard (cost_dashboard.py). \
         Set AGENT_COST_DASHBOARD_DIR or keep the agent/ folder next to claude/."
            .to_string(),
    )
}

fn find_python() -> Result<(PathBuf, Vec<String>), String> {
    // Prefer the Windows launcher with an explicit 3.x request.
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

fn is_port_free(port: u16) -> bool {
    // If something already accepts connections, treat the port as busy.
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}").parse().unwrap(),
        Duration::from_millis(80),
    )
    .is_err()
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
        if TcpStream::connect_timeout(
            &format!("127.0.0.1:{port}").parse().unwrap(),
            Duration::from_millis(100),
        )
        .is_ok()
        {
            return true;
        }
        thread::sleep(READY_POLL);
    }
    false
}

fn spawn_dashboard(agent_dir: &Path, port: u16) -> Result<Child, String> {
    let script = agent_dir.join("cost_dashboard.py");
    if !script.is_file() {
        return Err(format!("Missing script: {}", script.display()));
    }

    let (python, prefix_args) = find_python()?;
    let mut args = prefix_args;
    args.push(script.to_string_lossy().to_string());
    // Security: always bind loopback only. Never 0.0.0.0 from the desktop shell.
    args.push("--host".to_string());
    args.push("127.0.0.1".to_string());
    args.push("--port".to_string());
    args.push(port.to_string());

    let mut cmd = Command::new(&python);
    cmd.args(&args)
        .current_dir(agent_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // Avoid flashing a console window on Windows.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn()
        .map_err(|e| format!("Failed to start cost dashboard with {:?}: {e}", python))
}

fn stop_running(running: &mut RunningDashboard) {
    let _ = running.child.kill();
    let _ = running.child.wait();
}

/// Start the sidecar if needed and open the dashboard in the system browser.
#[tauri::command]
pub async fn open_cost_dashboard(
    state: State<'_, CostDashboardState>,
) -> Result<CostDashboardOpenResult, String> {
    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;

    // Reuse a still-alive process.
    if let Some(running) = guard.as_mut() {
        match running.child.try_wait() {
            Ok(None) => {
                let url = format!("http://127.0.0.1:{}", running.port);
                tauri_plugin_opener::open_url(&url, None::<String>)
                    .map_err(|e| format!("Failed to open browser: {e}"))?;
                return Ok(CostDashboardOpenResult {
                    url,
                    port: running.port,
                    started: false,
                });
            }
            Ok(Some(_)) | Err(_) => {
                *guard = None;
            }
        }
    }

    let agent_dir = resolve_agent_dir()?;
    let port = pick_port()?;
    let mut child = spawn_dashboard(&agent_dir, port)?;

    if !wait_until_ready(port) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(format!(
            "Cost dashboard did not become ready on 127.0.0.1:{port} within {}s",
            READY_TIMEOUT.as_secs()
        ));
    }

    let url = format!("http://127.0.0.1:{port}");
    tauri_plugin_opener::open_url(&url, None::<String>)
        .map_err(|e| format!("Failed to open browser: {e}"))?;

    *guard = Some(RunningDashboard { child, port });

    Ok(CostDashboardOpenResult {
        url,
        port,
        started: true,
    })
}

/// Stop the sidecar process if it is running.
#[tauri::command]
pub async fn stop_cost_dashboard(
    state: State<'_, CostDashboardState>,
) -> Result<bool, String> {
    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;

    if let Some(mut running) = guard.take() {
        stop_running(&mut running);
        return Ok(true);
    }
    Ok(false)
}

/// Query whether the sidecar is currently running.
#[tauri::command]
pub async fn cost_dashboard_status(
    state: State<'_, CostDashboardState>,
) -> Result<CostDashboardStatus, String> {
    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "Cost dashboard state lock poisoned".to_string())?;

    if let Some(running) = guard.as_mut() {
        match running.child.try_wait() {
            Ok(None) => {
                return Ok(CostDashboardStatus {
                    running: true,
                    url: Some(format!("http://127.0.0.1:{}", running.port)),
                    port: Some(running.port),
                    pid: Some(running.child.id()),
                });
            }
            Ok(Some(_)) | Err(_) => {
                *guard = None;
            }
        }
    }

    Ok(CostDashboardStatus {
        running: false,
        url: None,
        port: None,
        pid: None,
    })
}

/// Kill the sidecar on app exit (best-effort).
pub fn shutdown_cost_dashboard(state: &CostDashboardState) {
    if let Ok(mut guard) = state.inner.lock() {
        if let Some(mut running) = guard.take() {
            stop_running(&mut running);
        }
    }
}
