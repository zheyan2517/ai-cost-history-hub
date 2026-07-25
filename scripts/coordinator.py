#!/usr/bin/env python3
"""
AI Cost History Hub coordinator.

Starts the local cost dashboard (loopback only), serves a small portal,
and reports desktop-app readiness. Pure Python stdlib (3.12+).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
PID_FILE = ROOT / ".runtime" / "cost-dashboard.pid"
LOG_FILE = ROOT / ".runtime" / "cost-dashboard.log"
STATE_FILE = ROOT / ".runtime" / "state.json"


def load_config() -> dict:
    defaults = {
        "costDashboard": {
            "host": "127.0.0.1",
            "port": 8753,
            "portRange": 20,
            "readyTimeoutSec": 15,
        },
        "portal": {"host": "127.0.0.1", "port": 8740},
        "paths": {
            "agentDir": "agent",
            "claudeDir": "claude",
            "dashboardScript": "cost_dashboard.py",
        },
    }
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        # shallow merge
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
            elif isinstance(value, dict):
                merged = dict(value)
                merged.update(data[key])
                data[key] = merged
        return data
    return defaults


def find_python() -> list[str]:
    if os.name == "nt":
        py = shutil.which("py")
        if py:
            return [py, "-3"]
    for name in ("python", "python3"):
        path = shutil.which(name)
        if path:
            return [path]
    raise RuntimeError("Python 3.12+ not found on PATH (need python or py -3)")


def agent_dir(cfg: dict) -> Path:
    env = os.environ.get("AGENT_COST_DASHBOARD_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / cfg["paths"]["dashboardScript"]).is_file():
            return p
        raise RuntimeError(f"AGENT_COST_DASHBOARD_DIR invalid: {p}")
    p = (ROOT / cfg["paths"]["agentDir"]).resolve()
    if not (p / cfg["paths"]["dashboardScript"]).is_file():
        raise RuntimeError(f"cost_dashboard.py not found under {p}")
    return p


def port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def pick_port(host: str, start: int, span: int) -> int:
    for port in range(start, start + span):
        if not port_open(host, port):
            return port
    raise RuntimeError(f"No free port in {start}-{start + span - 1}")


def wait_ready(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    url = f"http://{host}:{port}/"
    while time.time() < deadline:
        if port_open(host, port) and http_ok(url):
            return True
        time.sleep(0.2)
    return False


def read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # Avoid text mode: tasklist may emit the active OEM code page.
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                check=False,
            )
            blob = (out.stdout or b"") + (out.stderr or b"")
            return str(pid).encode("ascii") in blob
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def stop_cost_dashboard() -> bool:
    pid = read_pid()
    stopped = False
    if pid and process_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            stopped = True
        except OSError:
            pass
        # Brief wait so the port is released before a restart.
        for _ in range(20):
            if not process_alive(pid):
                break
            time.sleep(0.1)
    if PID_FILE.is_file():
        PID_FILE.unlink(missing_ok=True)
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state["costDashboard"] = {"running": False}
            write_state(state)
        except (json.JSONDecodeError, OSError):
            pass
    return stopped


def ensure_cost_dashboard(cfg: dict, open_browser: bool = False) -> dict:
    host = cfg["costDashboard"]["host"]
    preferred = int(cfg["costDashboard"]["port"])
    span = int(cfg["costDashboard"]["portRange"])
    timeout = float(cfg["costDashboard"]["readyTimeoutSec"])

    # Reuse managed process
    pid = read_pid()
    if pid and process_alive(pid):
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            port = int(state.get("costDashboard", {}).get("port", preferred))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            port = preferred
        url = f"http://{host}:{port}/"
        if http_ok(url):
            info = {
                "running": True,
                "started": False,
                "url": url.rstrip("/"),
                "port": port,
                "pid": pid,
                "reused": "managed",
            }
            if open_browser:
                webbrowser.open(info["url"])
            return info

    # Reuse external instance already listening on preferred port
    if port_open(host, preferred) and http_ok(f"http://{host}:{preferred}/"):
        info = {
            "running": True,
            "started": False,
            "url": f"http://{host}:{preferred}",
            "port": preferred,
            "pid": None,
            "reused": "external",
        }
        if open_browser:
            webbrowser.open(info["url"])
        return info

    port = pick_port(host, preferred, span)
    a_dir = agent_dir(cfg)
    script = a_dir / cfg["paths"]["dashboardScript"]
    python_cmd = find_python()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fh = LOG_FILE.open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    cmd = [
        *python_cmd,
        str(script),
        "--host",
        host,
        "--port",
        str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(a_dir),
        stdin=subprocess.DEVNULL,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    log_fh.close()
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    if not wait_ready(host, port, timeout):
        try:
            proc.kill()
        except OSError:
            pass
        tail = ""
        if LOG_FILE.is_file():
            tail = LOG_FILE.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError(
            f"Cost dashboard failed to become ready on {host}:{port}.\nLog tail:\n{tail}"
        )

    info = {
        "running": True,
        "started": True,
        "url": f"http://{host}:{port}",
        "port": port,
        "pid": proc.pid,
        "reused": None,
    }
    write_state(
        {
            "costDashboard": {
                "running": True,
                "url": info["url"],
                "port": port,
                "pid": proc.pid,
            },
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    if open_browser:
        webbrowser.open(info["url"])
    return info


def desktop_status(cfg: dict) -> dict:
    claude = (ROOT / cfg["paths"]["claudeDir"]).resolve()
    package_json = claude / "package.json"
    node_modules = claude / "node_modules"
    tauri = claude / "src-tauri"
    has_pnpm = shutil.which("pnpm") is not None
    has_cargo = shutil.which("cargo") is not None or (
        Path.home() / ".cargo" / "bin" / "cargo.exe"
    ).is_file()
    return {
        "path": str(claude),
        "present": package_json.is_file() and tauri.is_dir(),
        "depsInstalled": node_modules.is_dir(),
        "pnpmAvailable": has_pnpm,
        "cargoAvailable": has_cargo,
        "canDev": has_pnpm and has_cargo and node_modules.is_dir(),
        "devHint": f'cd "{claude}" && pnpm install && pnpm tauri:dev',
    }


def portal_html(cost: dict, desktop: dict) -> str:
    cost_url = cost.get("url") or "http://127.0.0.1:8753"
    cost_ok = bool(cost.get("running"))
    desktop_ready = desktop.get("canDev")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Cost History Hub</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #1f3a32;
      --muted: #5a7369;
      --ok: #1f7a52;
      --warn: #a66b12;
      --accent: #2f7d9a;
      --glass: rgba(255, 252, 248, 0.82);
      --border: rgba(90, 130, 110, 0.22);
      --shadow: 0 10px 30px rgba(47, 90, 72, 0.1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      min-height: 100vh;
      background-color: #dcebe4;
      background-image:
        linear-gradient(160deg, rgba(255,250,245,0.78) 0%, rgba(220,236,230,0.58) 50%, rgba(210,228,236,0.68) 100%),
        url("/bg.jpg");
      background-size: cover;
      background-position: center;
      background-attachment: fixed;
    }}
    header {{
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center;
      background: rgba(255, 252, 248, 0.78);
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
    }}
    h1 {{ margin: 0; font-size: 18px; font-weight: 650; letter-spacing: 0.2px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    main {{ display: grid; grid-template-columns: 320px 1fr; min-height: calc(100vh - 64px); }}
    aside {{
      border-right: 1px solid var(--border);
      padding: 16px;
      background: rgba(238, 246, 242, 0.72);
      backdrop-filter: blur(10px);
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
      background: var(--glass);
      box-shadow: var(--shadow);
    }}
    .card h2 {{ margin: 0 0 8px; font-size: 14px; color: #23483c; }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px;
      border: 1px solid var(--border); background: rgba(255,255,255,0.7);
    }}
    .badge.ok {{ color: var(--ok); border-color: rgba(31,122,82,0.35); background: rgba(210,240,224,0.85); }}
    .badge.warn {{ color: var(--warn); border-color: rgba(166,107,18,0.35); background: rgba(255,236,204,0.9); }}
    a.btn, button.btn {{
      display: inline-block; margin-top: 10px; margin-right: 8px;
      padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border);
      background: rgba(255,255,255,0.88); color: var(--text); text-decoration: none; cursor: pointer;
      font-size: 13px; box-shadow: 0 2px 8px rgba(47,90,72,0.06);
    }}
    a.btn.primary {{
      background: linear-gradient(135deg, #3a9b7a, #2f7d9a);
      border-color: transparent; color: #fff;
    }}
    a.btn:hover {{ filter: brightness(1.03); }}
    section {{ background: transparent; }}
    iframe {{
      width: 100%; height: calc(100vh - 64px); border: 0;
      background: transparent; border-radius: 0;
    }}
    code {{ font-size: 12px; color: #2a5f6e; background: rgba(255,255,255,0.55); padding: 1px 4px; border-radius: 4px; }}
    ul {{ margin: 8px 0 0 18px; padding: 0; color: var(--muted); font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AI Cost History Hub</h1>
      <div class="muted">Session history + cost analytics · local only (127.0.0.1)</div>
    </div>
    <div class="muted">Status in sidebar · press F5 to refresh</div>
  </header>
  <main>
    <aside>
      <div class="card">
        <h2>Cost Dashboard</h2>
        <span class="badge {"ok" if cost_ok else "warn"}">{"Running" if cost_ok else "Not ready"}</span>
        <div class="muted" style="margin-top:8px">URL: <code>{cost_url}</code></div>
        <a class="btn primary" href="{cost_url}" target="_blank" rel="noreferrer">Open in new window</a>
        <a class="btn" href="/api/restart-cost">Restart dashboard</a>
      </div>
      <div class="card">
        <h2>History Viewer</h2>
        <span class="badge {"ok" if desktop_ready else "warn"}">{"Ready for dev" if desktop_ready else "Dependencies needed"}</span>
        <ul>
          <li>Path: <code>{desktop.get("path")}</code></li>
          <li>pnpm: {"yes" if desktop.get("pnpmAvailable") else "no"}</li>
          <li>cargo/Rust: {"yes" if desktop.get("cargoAvailable") else "no"}</li>
          <li>node_modules: {"yes" if desktop.get("depsInstalled") else "no"}</li>
        </ul>
        <div class="muted" style="margin-top:8px">Desktop dev command:</div>
        <code style="display:block;margin-top:6px;word-break:break-all">{desktop.get("devHint")}</code>
        <p class="muted" style="margin-top:10px">In the desktop app, use the Cost Dashboard control in the top bar (Tauri required).</p>
      </div>
      <div class="card">
        <h2>Security</h2>
        <ul>
          <li>Binds to 127.0.0.1 only</li>
          <li>Read-only access to local session data</li>
          <li>Lifecycle managed by coordinator / desktop app</li>
        </ul>
      </div>
    </aside>
    <section>
      <iframe src="{cost_url}" title="Cost Dashboard"></iframe>
    </section>
  </main>
</body>
</html>
"""


class PortalHandler(BaseHTTPRequestHandler):
    cfg: dict
    cost_info: dict

    def log_message(self, fmt: str, *args) -> None:  # quieter
        sys.stderr.write(f"[portal] {self.address_string()} {fmt % args}\n")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/status"):
            desktop = desktop_status(self.cfg)
            self._json(200, {"costDashboard": self.cost_info, "desktop": desktop})
            return
        if self.path.startswith("/api/restart-cost"):
            stop_cost_dashboard()
            try:
                self.cost_info = ensure_cost_dashboard(self.cfg, open_browser=False)
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
            except Exception as e:  # noqa: BLE001
                self._json(500, {"error": str(e)})
            return
        if self.path in ("/bg.jpg", "/assets/bg.jpg"):
            bg = ROOT / "scripts" / "bg.jpg"
            if not bg.is_file():
                bg = ROOT / "agent" / "assets" / "bg.jpg"
            if not bg.is_file():
                self.send_error(404)
                return
            data = bg.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path in ("/", "/index.html"):
            html = portal_html(self.cost_info, desktop_status(self.cfg)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        self.send_error(404)


def serve_portal(cfg: dict, cost_info: dict) -> None:
    host = cfg["portal"]["host"]
    port = int(cfg["portal"]["port"])
    handler = type(
        "BoundPortalHandler",
        (PortalHandler,),
        {"cfg": cfg, "cost_info": cost_info},
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"[portal] serving {url}")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[portal] shutting down...")
    finally:
        httpd.server_close()


def cmd_status(cfg: dict) -> int:
    cost = {"running": False}
    host = cfg["costDashboard"]["host"]
    port = int(cfg["costDashboard"]["port"])
    if port_open(host, port) and http_ok(f"http://{host}:{port}/"):
        cost = {"running": True, "url": f"http://{host}:{port}", "port": port}
    payload = {"costDashboard": cost, "desktop": desktop_status(cfg)}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_start(cfg: dict, with_portal: bool, open_browser: bool) -> int:
    info = ensure_cost_dashboard(cfg, open_browser=open_browser and not with_portal)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if with_portal:
        # keep child alive: portal thread blocks main
        serve_portal(cfg, info)
    return 0


def cmd_stop() -> int:
    stopped = stop_cost_dashboard()
    print(json.dumps({"stopped": stopped}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Cost History Hub coordinator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Start cost dashboard (+ optional portal)")
    p_start.add_argument("--portal", action="store_true", help="Serve unified portal")
    p_start.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically",
    )

    sub.add_parser("stop", help="Stop managed cost dashboard")
    sub.add_parser("status", help="Print readiness JSON")
    sub.add_parser("open-cost", help="Ensure cost dashboard and open browser")

    args = parser.parse_args(argv)
    cfg = load_config()

    try:
        if args.cmd == "start":
            return cmd_start(
                cfg,
                with_portal=args.portal,
                open_browser=not args.no_browser,
            )
        if args.cmd == "stop":
            return cmd_stop()
        if args.cmd == "status":
            return cmd_status(cfg)
        if args.cmd == "open-cost":
            info = ensure_cost_dashboard(cfg, open_browser=True)
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"[error] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
