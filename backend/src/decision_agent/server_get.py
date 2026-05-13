from __future__ import annotations

import json
import re
from http import HTTPStatus
from pathlib import Path

from decision_agent.modules.architectures.registry import list_architectures
from decision_agent.modules.evaluation.runner import CONDITION_MAP, get_benchmark, list_benchmarks, list_fixtures
from decision_agent.modules.runs.service import read_run, read_runs
from decision_agent.server_runtime import ROOT

class GetRoutesMixin:
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._send_json(
                {
                    "architectures": list_architectures(),
                    "runs": read_runs(ROOT),
                }
            )
            return
        if parsed.path == "/api/benchmarks":
            self._send_json(
                {
                    "fixtures": list_fixtures(),
                    "conditions": list(CONDITION_MAP.keys()),
                    "benchmarks": list_benchmarks(ROOT),
                }
            )
            return
        m = re.fullmatch(r"/api/benchmarks/([^/]+)", parsed.path)
        if m:
            benchmark_id = m.group(1)
            state = get_benchmark(benchmark_id)
            if state is None:
                progress = ROOT / "data" / "benchmarks" / benchmark_id / "progress.json"
                if progress.exists():
                    state = json.loads(progress.read_text(encoding="utf-8"))
            if state is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Benchmark not found")
                return
            self._send_json(state)
            return
        m = re.fullmatch(r"/api/runs/([^/]+)/scope", parsed.path)
        if m:
            run = read_run(m.group(1), ROOT)
            if not run:
                self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self._send_json(run.get("scope") or {})
            return
        m = re.fullmatch(r"/api/runs/([^/]+)/evidence", parsed.path)
        if m:
            run = read_run(m.group(1), ROOT)
            if not run:
                self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self._send_json(run.get("evidence") or {})
            return
        m = re.fullmatch(r"/api/runs/([^/]+)/authorization", parsed.path)
        if m:
            run = read_run(m.group(1), ROOT)
            if not run:
                self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self._send_json({"receipts": run.get("authorization") or []})
            return
        m = re.fullmatch(r"/api/runs/([^/]+)", parsed.path)
        if m:
            run = read_run(m.group(1), ROOT)
            if not run:
                self.send_error(HTTPStatus.NOT_FOUND, "Run not found")
                return
            self._send_json(run)
            return
        if self._static_path(self.path) is None:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        super().do_GET()
