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
            self._handle_benchmark_create()
            return

        if path == "/api/task-suggestions":
            self._handle_task_suggestion()
            return

        if path == "/api/task-suggestions/refine":
            self._handle_task_suggestion_refine()
            return

        if path == "/api/runs":
            self._handle_run_create()
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/start", path)
        if m:
            self._handle_run_start(m.group(1))
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/build", path)
        if m:
            self._handle_architecture_build(m.group(1))
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/approve", path)
        if m:
            self._handle_architecture_approve(m.group(1))
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/reject", path)
        if m:
            self._handle_architecture_reject(m.group(1))
            return

        m = re.fullmatch(r"/api/runs/([^/]+)/architecture/generate-contracts", path)
        if m:
            self._handle_architecture_generate_contracts(m.group(1))
            return

        if handle_worker_post(self, path):
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _send_bad_request(self, code: str, error: Exception) -> None:
        self._send_json(
            {"error": {"code": code, "message": str(error)}},
            status=HTTPStatus.BAD_REQUEST,
        )

    def _handle_benchmark_create(self) -> None:
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
            self._send_bad_request("benchmark_failed", error)
            return
        self._send_json({"benchmark_id": benchmark_id, "status": "started"}, status=HTTPStatus.CREATED)

    def _handle_task_suggestion(self) -> None:
        try:
            task = self._read_body()
            suggestion = suggest_task_setup(task, ROOT, get_provider())
        except Exception as error:
            self._send_bad_request("task_suggestion_failed", error)
            return
        self._send_json(suggestion)

    def _handle_task_suggestion_refine(self) -> None:
        try:
            body = self._read_body()
            task = body.get("task", {})
            answers = body.get("answers", [])
            suggestion = suggest_task_setup_with_answers(task, answers, ROOT, get_provider())
        except Exception as error:
            self._send_bad_request("task_suggestion_failed", error)
            return
        self._send_json(suggestion)

    def _handle_run_create(self) -> None:
        try:
            body = self._read_body()
            task, layer_config, provider_override, benchmark_mode = _parse_run_create_body(body)
            run = create_run(
                task,
                ROOT,
                layer_config=layer_config,
                provider_override=provider_override,
                benchmark_mode=benchmark_mode,
            )
        except Exception as error:
            self._send_bad_request("run_create_failed", error)
            return
        self._send_json(run, status=HTTPStatus.CREATED)

    def _handle_run_start(self, run_id: str) -> None:
        try:
            run = start_run(run_id, ROOT)
        except Exception as error:
            self._send_bad_request("start_failed", error)
            return
        self._send_json(run)

    def _handle_architecture_build(self, run_id: str) -> None:
        try:
            body = self._read_body()
            prebuilt_artifact = body.get("artifact") or None
            run = build_architecture_proposal(
                run_id,
                ROOT,
                get_provider(),
                prebuilt_artifact=prebuilt_artifact,
            )
        except Exception as error:
            self._send_bad_request("architecture_build_failed", error)
            return
        self._send_json(run)

    def _handle_architecture_approve(self, run_id: str) -> None:
        try:
            body = self._read_body()
            run = approve_architecture(run_id, body.get("note", ""), ROOT)
        except Exception as error:
            self._send_bad_request("architecture_approve_failed", error)
            return
        self._send_json(run)

    def _handle_architecture_reject(self, run_id: str) -> None:
        try:
            body = self._read_body()
            run = reject_architecture(run_id, body.get("reason", ""), ROOT)
        except Exception as error:
            self._send_bad_request("architecture_reject_failed", error)
            return
        self._send_json(run)

    def _handle_architecture_generate_contracts(self, run_id: str) -> None:
        try:
            run = generate_contracts_for_approved_architecture(run_id, ROOT)
        except Exception as error:
            self._send_bad_request("contracts_generation_failed", error)
            return
        self._send_json(run)


def _parse_run_create_body(body: dict) -> tuple[dict, dict | None, str | None, bool]:
    if "task" in body and isinstance(body.get("task"), dict):
        return (
            body["task"],
            body.get("layer_config"),
            body.get("provider_override"),
            bool(body.get("benchmark_mode", False)),
        )
    return body, None, None, False
