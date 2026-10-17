#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "0.3"
APP_ID = "eme-pc-remote"

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
WEB_DIR = BASE / "web"
LOG_PATH = BASE / "EmePCRemote.log"
START_TIME = time.time()
SERVER = None

DEFAULT_CONFIG = {
    "name": "Eme PC",
    "port": 8765,
    "token": "",
    "apps": {
        "Chrome": 'cmd /c start "" chrome',
        "Discord": 'cmd /c start "" discord://-/'
    },
    "wake": {
        "enabled": False,
        "note": "GS-BE7200X導入後に設定予定"
    },
    "update": {
        "repo": "",
        "branch": "main"
    }
}

def log_line(message: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        if sys.stdout is not None:
            print(line, flush=True)
    except Exception:
        pass

def save_config(cfg):
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    changed = False

    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        changed = True
    for key in ("name", "port", "apps", "wake"):
        if key not in cfg:
            cfg[key] = DEFAULT_CONFIG[key]
            changed = True

    if not isinstance(cfg.get("update"), dict):
        cfg["update"] = {"repo": "", "branch": "main"}
        changed = True
    if "repo" not in cfg["update"]:
        cfg["update"]["repo"] = ""
        changed = True
    if "branch" not in cfg["update"]:
        cfg["update"]["branch"] = "main"
        changed = True

    if changed:
        save_config(cfg)
    return cfg

CONFIG = load_config()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()

def run_windows(command):
    if os.name != "nt":
        raise RuntimeError("この操作はWindowsでのみ実行できます。")
    subprocess.Popen(command, shell=True)

def launch_app(name):
    cmd = CONFIG.get("apps", {}).get(name)
    if not cmd:
        raise ValueError("未登録のアプリです。")
    run_windows(cmd)

def parse_version(value):
    value = str(value or "").strip().lower().lstrip("v")
    nums = []
    for part in value.split("."):
        m = ""
        for c in part:
            if c.isdigit():
                m += c
            else:
                break
        nums.append(int(m or 0))
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])

def validate_repo(repo):
    repo = str(repo or "").strip()
    if not repo:
        raise ValueError("更新元GitHubが未設定です。")
    if not re_fullmatch_repo(repo):
        raise ValueError("GitHubは owner/repo の形式で設定してください。")
    return repo

def re_fullmatch_repo(repo):
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        return False
    return all(all(c in allowed for c in p) for p in parts)

def raw_url(repo, branch, path):
    safe_path = "/".join(urllib.parse.quote(x, safe="._-") for x in path.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(branch, safe='._-')}/{safe_path}"

def http_get_bytes(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"EmePCRemote/{VERSION}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def get_manifest():
    repo = validate_repo(CONFIG.get("update", {}).get("repo", ""))
    branch = str(CONFIG.get("update", {}).get("branch", "main") or "main")
    url = raw_url(repo, branch, "update/manifest.json")
    try:
        data = json.loads(http_get_bytes(url).decode("utf-8"))
    except Exception as e:
        raise ValueError(f"更新情報を取得できません: {e}")

    if data.get("app_id") != APP_ID:
        raise ValueError("更新情報がEme PC Remote用ではありません。")
    if not isinstance(data.get("files"), list) or not data["files"]:
        raise ValueError("更新ファイル一覧が不正です。")
    return repo, branch, data

def validate_relpath(path):
    path = str(path).replace("\\", "/")
    p = Path(path)
    if not path or p.is_absolute() or ".." in p.parts:
        raise ValueError(f"不正な更新パス: {path}")
    blocked = {"config.json", "EmePCRemote.log"}
    if path in blocked:
        raise ValueError(f"保護ファイルは更新できません: {path}")
    return path

def check_update():
    repo, branch, manifest = get_manifest()
    latest = str(manifest.get("version", "")).strip()
    if not latest:
        raise ValueError("更新バージョンがありません。")
    return {
        "current": VERSION,
        "latest": latest,
        "available": parse_version(latest) > parse_version(VERSION),
        "repo": repo,
        "branch": branch,
        "notes": str(manifest.get("notes", ""))
    }

def choose_pythonw():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)
    candidate = exe.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    return str(exe)

def prepare_update():
    repo, branch, manifest = get_manifest()
    latest = str(manifest.get("version", "")).strip()
    if parse_version(latest) <= parse_version(VERSION):
        return {"already_latest": True, "version": latest}

    tmp = Path(tempfile.mkdtemp(prefix="eme_pc_remote_update_"))
    payload = tmp / "payload"
    payload.mkdir(parents=True, exist_ok=True)

    for item in manifest["files"]:
        if isinstance(item, str):
            rel = validate_relpath(item)
            expected_sha = ""
        elif isinstance(item, dict):
            rel = validate_relpath(item.get("path", ""))
            expected_sha = str(item.get("sha256", "")).lower().strip()
        else:
            raise ValueError("更新ファイル一覧が不正です。")

        url = raw_url(repo, branch, f"update/{rel}")
        data = http_get_bytes(url, timeout=30)

        if expected_sha:
            import hashlib
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected_sha:
                raise ValueError(f"更新ファイルの検証に失敗: {rel}")

        dest = payload / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    helper = BASE / "apply_update.py"
    if not helper.exists():
        raise ValueError("apply_update.py が見つかりません。")

    args = [
        choose_pythonw(),
        str(helper),
        "--pid", str(os.getpid()),
        "--source", str(payload),
        "--target", str(BASE),
        "--restart", str(BASE / "start_hidden.vbs")
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(args, cwd=str(BASE), creationflags=flags)
    return {"already_latest": False, "version": latest}

class Handler(BaseHTTPRequestHandler):
    server_version = f"EmePCRemote/{VERSION}"

    def log_message(self, fmt, *args):
        log_line(f"{self.client_address[0]} - {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Eme-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path, content_type):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, body=None):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        q_token = qs.get("token", [""])[0]
        h_token = self.headers.get("X-Eme-Token", "")
        b_token = (body or {}).get("token", "") if isinstance(body, dict) else ""
        return secrets.compare_digest(str(CONFIG["token"]), str(q_token or h_token or b_token))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/api/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, 401)
                return
            self._send_json({
                "ok": True,
                "version": VERSION,
                "online": True,
                "name": CONFIG.get("name", "Eme PC"),
                "hostname": socket.gethostname(),
                "ip": get_local_ip(),
                "uptime_seconds": int(time.time() - START_TIME),
                "wake_ready": bool(CONFIG.get("wake", {}).get("enabled", False)),
                "apps": list(CONFIG.get("apps", {}).keys()),
                "update_repo": CONFIG.get("update", {}).get("repo", ""),
                "update_branch": CONFIG.get("update", {}).get("branch", "main")
            })
            return

        if path == "/api/update/check":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, 401)
                return
            try:
                self._send_json({"ok": True, **check_update()})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
            return

        self.send_error(404)

    def do_POST(self):
        global CONFIG, SERVER
        parsed = urllib.parse.urlparse(self.path)

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"))
        except Exception:
            self._send_json({"ok": False, "error": "bad_json"}, 400)
            return

        if not self._authorized(body):
            self._send_json({"ok": False, "error": "unauthorized"}, 401)
            return

        if parsed.path == "/api/update/config":
            repo = str(body.get("repo", "")).strip()
            branch = str(body.get("branch", "main")).strip() or "main"
            if repo and not re_fullmatch_repo(repo):
                self._send_json({"ok": False, "error": "owner/repo の形式で入力してください。"}, 400)
                return
            CONFIG.setdefault("update", {})["repo"] = repo
            CONFIG["update"]["branch"] = branch
            save_config(CONFIG)
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/update/install":
            try:
                result = prepare_update()
                if result.get("already_latest"):
                    self._send_json({"ok": True, "already_latest": True})
                    return
                self._send_json({"ok": True, "installing": True, "version": result["version"]})

                def stop_server():
                    time.sleep(0.8)
                    if SERVER:
                        SERVER.shutdown()
                threading.Thread(target=stop_server, daemon=True).start()
            except Exception as e:
                log_line(f"update error: {e}")
                self._send_json({"ok": False, "error": str(e)}, 400)
            return

        if parsed.path != "/api/action":
            self.send_error(404)
            return

        action = body.get("action", "")
        try:
            if action == "lock":
                run_windows("rundll32.exe user32.dll,LockWorkStation")
            elif action == "shutdown":
                self._send_json({"ok": True, "message": "シャットダウンします"})
                threading.Timer(0.6, lambda: run_windows("shutdown /s /t 0")).start()
                return
            elif action == "restart":
                self._send_json({"ok": True, "message": "再起動します"})
                threading.Timer(0.6, lambda: run_windows("shutdown /r /t 0")).start()
                return
            elif action == "launch":
                launch_app(str(body.get("app", "")))
            elif action == "wake":
                self._send_json({
                    "ok": False,
                    "error": "wake_not_configured",
                    "message": "PC起動はGS-BE7200X導入後に接続します。"
                }, 409)
                return
            else:
                self._send_json({"ok": False, "error": "unknown_action"}, 400)
                return
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
            return

        self._send_json({"ok": True})

def main():
    global SERVER
    port = int(CONFIG.get("port", 8765))
    ip = get_local_ip()
    log_line(f"Eme PC Remote v{VERSION} start - {ip}:{port}")
    SERVER = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SERVER.server_close()

if __name__ == "__main__":
    main()
