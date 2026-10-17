#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

def process_exists(pid):
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                text=True,
                errors="ignore"
            )
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def copy_payload(src, target):
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        if p.is_dir():
            (target / rel).mkdir(parents=True, exist_ok=True)
            continue
        if rel.as_posix() in ("config.json", "EmePCRemote.log"):
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--restart", required=True)
    args = ap.parse_args()

    for _ in range(80):
        if not process_exists(args.pid):
            break
        time.sleep(0.25)

    time.sleep(0.5)
    copy_payload(Path(args.source), Path(args.target))

    if os.name == "nt":
        subprocess.Popen(
            ["wscript.exe", args.restart],
            cwd=args.target,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

if __name__ == "__main__":
    main()
