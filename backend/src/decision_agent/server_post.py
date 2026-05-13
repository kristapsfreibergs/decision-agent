from __future__ import annotations

import re
import threading
from http import HTTPStatus
from urllib.parse import urlparse

from decision_agent.modules.decisions.suggestions import suggest_task_setup, suggest_task_setup_with_answers
from decision_agent.modules.evaluation.runner import CONDITION_MAP, list_fixtures, run_benchmark
from decision_agent.modules.runs.service import approve_architecture, build_architecture_proposal, create_run, generate_contracts_for_approved_architecture, reject_architecture, start_run
from decision_agent.server_post_workers import handle_worker_post
from decision_agent.server_runtime import ROOT
from decision_agent.shared.providers.registry import get_provider

class PostRoutesMixin:
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/benchmarks":
            try:
                body = self._read_body()
                conditions = body.get("conditions") or list(CONDITION_MAP.keys())
                fixtures = body.get("fixtures") or list_fixtures()
                reps = int(body.get("reps", 3))
                timeout = float(body.get("timeout_seconds", 300))
                unknown = [c for c in conditions if c not in CONDITION_MAP]
                if unknown:
                    raise ValueError(f"Unknown conditions: {unknown}")
                benchmark_id = run_benchmark(conditions, fixtures, reps, ROOT, timeout)
            except Exception as error:
                self._send_json(
                    {"error": {"code": "benchmark_failed", "message": str(error)}},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json({"benchmark_id": benchmark_id, "status": "started"}, status=HTTPStatus.CREATED)
            return

        if path == "/api/task-suggestions":
            try:
                task = self._read_body()
                suggestion = suggest_task_setup(task, ROOT, get_provider())
            except Exception as error:
                self._send_json(
                    {"error": {"code": "task_suggestion_failed", "message": str(error)}},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(suggestion)
            return

        if path == "/api/task-suggestions/refine":
            try:
                body = self._read_body()
                task = body.get("task", {})
                answers = body.get("answers", [])
                suggestion = suggest_task_setup_with_answers(task, answers, ROOT, get_provider())
            except Exception as error:
                self._send_json(
                    {"error": {"code": "task_suggestion_failed", "message": str(error)}},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(suggestion)
            return

        if path == "/api/runs":
            try:
                body = self._read_body()
                if "task" in body and isinstance(body.get("task"), dict):
                    task = body["task"]
                    layer_config = body.get("layer_config")
                    provider_override = body.get("provider_override")
                    benchmark_mode = bool(body.get("benchmark_mode", False))
                else:
                    task = body
                    layer_config = None
                    provider_override = None
                    benchmark_mode = False
                run = create_run(
                    task,
                    ROOT,
                    layer_config=layer_config,
                    provider_override=provider_override,
                    benchmark_mode=benchmark_mode,
                )
            except Exception as error:
                self._send_json(
                    {"error": {"code": "run_create_failed", "message": str(error)}},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(run, status=HTTPStatus.CREATED)
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/start", path)
        if m:
            run_id = m.group(1)
            try:
                run = start_run(run_id, ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "start_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/build", path)
        if m:
            run_id = m.group(1)
            try:
                body = self._read_body()
                prebuilt_artifact = body.get("artifact") or None
                run = build_architecture_proposal(run_id, ROOT, get_provider(), prebuilt_artifact=prebuilt_artifact)
            except Exception as error:
                self._send_json({"error": {"code": "architecture_build_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/approve", path)
        if m:
            run_id = m.group(1)
            try:
                body = self._read_body()
                run = approve_architecture(run_id, body.get("note", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "architecture_approve_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/reject", path)
        if m:
            run_id = m.group(1)
            try:
                body = self._read_body()
                run = reject_architecture(run_id, body.get("reason", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "architecture_reject_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/generate-contracts", path)
        if m:
            run_id = m.group(1)
            try:
                run = generate_contracts_for_approved_architecture(run_id, ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "contracts_generation_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        if handle_worker_post(self, path):
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")
