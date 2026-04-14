import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_DIR = ROOT_DIR / "runtime"
MANAGED_FILE = RUNTIME_DIR / "managed_agents.json"


def _ensure_runtime_dir():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_records():
    _ensure_runtime_dir()
    if not MANAGED_FILE.exists():
        return []
    try:
        return json.loads(MANAGED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_records(records):
    _ensure_runtime_dir()
    MANAGED_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_pid_running(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def list_managed_agents():
    records = _read_records()
    alive_records = []
    for record in records:
        record["running"] = _is_pid_running(record.get("pid"))
        alive_records.append(record)
    _write_records(alive_records)
    return alive_records


def launch_agent(alias=""):
    records = list_managed_agents()
    normalized_alias = str(alias or "").strip()

    for record in records:
        if record.get("running") and record.get("alias", "") == normalized_alias:
            return {
                "already_running": True,
                "pid": record.get("pid"),
                "log": record.get("log"),
                "alias": normalized_alias,
            }

    log_name = "agent.log" if not normalized_alias else f"agent-{normalized_alias}.log"
    log_path = RUNTIME_DIR / log_name

    uv_path = shutil.which("uv")
    if uv_path:
        command = [
            uv_path,
            "run",
            "--with-requirements",
            "agent/requirements.txt",
            "python",
            "agent/flaghunter.py",
        ]
    else:
        command = [sys.executable, "agent/flaghunter.py"]

    if normalized_alias:
        command.extend(["--name", normalized_alias])

    _ensure_runtime_dir()
    log_handle = open(log_path, "a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

    record = {
        "pid": process.pid,
        "alias": normalized_alias,
        "log": str(log_path),
    }
    records.append(record)
    _write_records(records)
    return {
        "already_running": False,
        **record,
    }


def stop_managed_agent(pid):
    target_pid = int(pid)
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(target_pid), "/T", "/F"], check=False)
    else:
        os.killpg(target_pid, signal.SIGTERM)

    records = [record for record in list_managed_agents() if int(record.get("pid", 0)) != target_pid]
    _write_records(records)
