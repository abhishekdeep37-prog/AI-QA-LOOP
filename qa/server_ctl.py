"""Start and stop a copy of the app under test (used by the runner and by patch verification)."""
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def running_server(app_dir, port=None, startup_timeout=15):
    """Run <app_dir>/server.py on a free port and yield its base URL."""
    app_dir = Path(app_dir).resolve()
    port = port or _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(app_dir / "server.py"), "--port", str(port)],
        cwd=app_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                err = proc.stderr.read().decode(errors="replace")[-800:]
                raise RuntimeError(f"app exited during startup:\n{err}")
            try:
                with urllib.request.urlopen(base_url + "/api/health", timeout=1):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("app did not become healthy in time")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
