"""本地阅读器 —— 把 data/walk 的结构化产物读成章节剧本。

用法：
  uv run python scripts/reader.py
  浏览器打开 http://127.0.0.1:8765

零依赖：stdlib http.server。只读，不改 walk 产物。
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WALK = ROOT / "data" / "walk"
CHAPTERS = WALK / "chapters"
STEPS = WALK / "steps"
STORES = WALK / "stores"
UI = Path(__file__).resolve().parent / "reader_ui"


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _step_out(step_folder: str, name: str):
    return _read_json(STEPS / step_folder / "out" / name)


def list_chapters() -> list[dict]:
    items = []
    if not CHAPTERS.exists():
        return items
    for d in sorted(CHAPTERS.iterdir()):
        m = re.fullmatch(r"c(\d+)", d.name)
        if not m:
            continue
        n = int(m.group(1))
        script = _read_json(d / "out" / "script.json")
        plan = _read_json(d / "out" / "plan.json")
        blocked = script is None and (d / "out" / "violations.json").exists()
        status = None
        if script:
            status = script.get("consistency_status", "clean")
        elif blocked:
            status = "blocked"
        items.append({
            "n": n,
            "id": f"c{n}",
            "theme": (script or plan or {}).get("theme") or "",
            "tone": (script or plan or {}).get("tone") or "",
            "status": status,
            "scenes": len((script or {}).get("scenes") or []),
            "has_script": script is not None,
        })
    return items


def chapter_payload(n: int) -> dict | None:
    d = CHAPTERS / f"c{n}"
    if not d.exists():
        return None
    out = d / "out"
    script = _read_json(out / "script.json")
    plan = _read_json(out / "plan.json")
    violations = _read_json(out / "violations.json") or []
    trace = _read_json(out / "trace.json") or []
    scene_script = _read_json(out / "scene_script.json")
    return {
        "n": n,
        "id": f"c{n}",
        "script": script,
        "plan": plan,
        "scene_script": scene_script,
        "violations": violations,
        "trace": trace,
        "blocked": script is None and bool(violations),
    }


def genesis_payload() -> dict:
    return {
        "seed": _step_out("00_g0", "seed.json"),
        "l0": _step_out("01_g1", "l0.json"),
        "l1": _step_out("01_g1", "l1.json"),
        "l2": _step_out("04_g4", "l2.json"),
        "world": _step_out("02_g2", "world.json"),
        "profiles": _step_out("05_g5", "profiles.json"),
        "store_counts": {
            "script": len(_read_jsonl(STORES / "script.jsonl")),
            "mem": len(_read_jsonl(STORES / "mem.jsonl")),
            "arc": len(_read_jsonl(STORES / "arc.jsonl")),
            "violation": len(_read_jsonl(STORES / "violation.jsonl")),
        },
    }


def overview() -> dict:
    seed = _step_out("00_g0", "seed.json") or {}
    return {
        "walk_root": str(WALK.resolve()),
        "logline": seed.get("logline") or "",
        "genre": seed.get("genre") or [],
        "chapters": list_chapters(),
        "genesis_ready": all(
            (STEPS / folder / "out" / name).exists()
            for folder, name in (
                ("00_g0", "seed.json"),
                ("01_g1", "l0.json"),
                ("01_g1", "l1.json"),
                ("04_g4", "l2.json"),
                ("05_g5", "profiles.json"),
            )
        ),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "StoryReader/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[reader] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            html = (UI / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/overview":
            self._json(200, overview())
            return
        if path == "/api/genesis":
            self._json(200, genesis_payload())
            return
        m = re.fullmatch(r"/api/chapters/(\d+)", path)
        if m:
            payload = chapter_payload(int(m.group(1)))
            if payload is None:
                self._json(404, {"error": "chapter not found"})
            else:
                self._json(200, payload)
            return
        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            file = UI / rel
            if file.is_file() and UI in file.resolve().parents:
                ctype = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                }.get(file.suffix, "application/octet-stream")
                self._send(200, file.read_bytes(), ctype)
                return
        self._json(404, {"error": "not found", "path": path})


def main() -> None:
    parser = argparse.ArgumentParser(description="Story Engine 本地阅读器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not UI.exists():
        raise SystemExit(f"缺少 UI 目录：{UI}")
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"阅读器：http://{args.host}:{args.port}")
    print(f"数据源：{WALK.resolve()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        httpd.server_close()


if __name__ == "__main__":
    main()
