from __future__ import annotations

import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from app.analyzer import analyze_message, render_markdown
from app.graph.workflow import run_full_check
from app.models import CaseInput, to_full_check_response

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, format: str, *args) -> None:  # quieter console
        print("[triage] " + format % args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/analyze", "/api/full-check"}:
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            text = str(payload.get("text", ""))
            if parsed.path == "/api/full-check":
                case = CaseInput(text=text)
                graph_state = run_full_check(case.text)
                graph_state["markdown"] = graph_state.get("final_report", "")
                result = to_full_check_response(graph_state).model_dump()
            else:
                result = analyze_message(text)
                result["markdown"] = render_markdown(result)
            self._json(200, result)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._json(500, {"error": str(exc)})


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Recruiter Risk Triage V1 running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
