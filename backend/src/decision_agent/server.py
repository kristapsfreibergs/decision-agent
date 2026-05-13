from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from decision_agent.server_get import GetRoutesMixin
from decision_agent.server_post import PostRoutesMixin
from decision_agent.server_runtime import SETTINGS, _can_execute_contract


class DecisionAgentHandler(GetRoutesMixin, PostRoutesMixin, SimpleHTTPRequestHandler):
    server_version = "DecisionAgentPython/0.1"

    def _static_path(self, request_path: str) -> Path | None:
        requested = unquote(urlparse(request_path).path)
        if requested == "/":
            requested = "/index.html"
        public_root = SETTINGS.public_dir.resolve()
        file_path = (public_root / requested.lstrip("/")).resolve()
        try:
            file_path.relative_to(public_root)
        except ValueError:
            return None
        return file_path

    def translate_path(self, path: str) -> str:
        file_path = self._static_path(path)
        if file_path is None:
            return str((SETTINGS.public_dir / "__forbidden__").resolve())
        return str(file_path)

    def end_headers(self) -> None:
        self.send_header("X-Request-ID", "local-dev")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    server = ThreadingHTTPServer((SETTINGS.host, SETTINGS.port), DecisionAgentHandler)
    print(f"Decision Agent GUI: http://{SETTINGS.host}:{SETTINGS.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
