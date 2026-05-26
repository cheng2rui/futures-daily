#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, re
from pathlib import Path

PATTERNS = {
    "persistence": re.compile(r"LaunchAgent|LaunchDaemon|crontab|systemctl|plist|登录项", re.I),
    "curl_pipe_shell": re.compile(r"curl\b[^\n|]*\|\s*(sh|bash)|wget\b[^\n|]*\|\s*(sh|bash)", re.I),
    "encoded_payload": re.compile(r"base64\s+(-d|--decode)|eval\s*\(|atob\s*\(", re.I),
    "dangerous_delete": re.compile(r"rm\s+-rf\s+(/|~|\$HOME|\.\.)", re.I),
    "secret_literal": re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]{8,}"),
}
SCAN_GLOBS = ["*.py", "*.js", "*.ts", "*.vue", "*.sh", "Dockerfile", "docker-compose.yml", "requirements.txt", "package-lock.json", "*.md", "*.yaml", "*.yml"]
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "data", "logs", "tmp", "web", "dist"}


def rec_id(kind, path, name):
    return kind + ":" + hashlib.sha256(f"{kind}|{path}|{name}".encode()).hexdigest()[:20]


def iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if any(p.match(g) or p.name == g for g in SCAN_GLOBS):
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--fail-on-high", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    findings = 0
    for p in iter_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(p.relative_to(root))
        if rel == "scripts/security_inventory.py" or rel.startswith("docs/"):
            continue
        for name, pat in PATTERNS.items():
            for m in pat.finditer(text):
                line = text[:m.start()].count("\n") + 1
                severity = "high" if name in {"persistence", "curl_pipe_shell", "dangerous_delete", "encoded_payload"} else "medium"
                findings += severity == "high"
                print(json.dumps({"record_type":"finding","record_id":rec_id("finding", rel, f"{name}:{line}"),"scanner":"futures-security-inventory","path":rel,"line":line,"rule":name,"severity":severity,"evidence":m.group(0)[:160]}, ensure_ascii=False))
    print(json.dumps({"record_type":"scan_summary","record_id":rec_id("scan_summary", str(root), str(findings)),"status":"complete" if not (args.fail_on_high and findings) else "error","high_findings":findings}, ensure_ascii=False))
    raise SystemExit(1 if args.fail_on_high and findings else 0)

if __name__ == "__main__":
    main()
