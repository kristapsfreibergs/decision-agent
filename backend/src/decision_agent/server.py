from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import re

from decision_agent.modules.architectures.registry import list_architectures
from decision_agent.modules.decisions.suggestions import suggest_task_setup, suggest_task_setup_with_answers
from decision_agent.modules.runs.service import (
    answer_worker,
    approve_architecture,
    build_architecture_proposal,
    create_run,
    gate_approve,
    gate_reject,
    generate_contracts_for_approved_architecture,
    post_worker_message,
    read_run,
    read_runs,
    reject_architecture,
    start_run,
)
from decision_agent.modules.workers.runner import run_worker
from decision_agent.settings import get_settings
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.registry import get_provider

ROOT = Path.cwd()
SETTINGS = get_settings(ROOT)
_ACTIVE_SCHEDULERS: set[str] = set()
_SCHEDULER_LOCK = threading.Lock()


def _execute_in_background(
    run_id: str,
    worker_id: str,
    contract: dict,
    audit_path: Path,
    root: Path,
    provider: object,
) -> None:
    try:
        run_worker(run_id, worker_id, contract, audit_path, root, provider)
    except Exception as exc:
        append_audit_event(
            audit_path,
            {
                "event": "worker_failed",
                "run_id": run_id,
                "worker_id": worker_id,
                "error": str(exc),
            },
        )


def _run_scheduler(run_id: str, root: Path, provider: object) -> None:
    from decision_agent.modules.runs.scheduler import (
        get_ready_worker_ids,
        has_active_workers,
        has_blocked_workers,
        is_run_complete,
    )

    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    try:
        append_audit_event(audit_path, {"event": "scheduler_started", "run_id": run_id})
        started: set[str] = set()

        for _ in range(120):
            run = read_run(run_id, root)
            if not run:
                break

            all_contracts = run.get("generated_contracts", []) or run.get("contracts", [])
            if not all_contracts:
                break
            if is_run_complete(run, all_contracts):
                append_audit_event(audit_path, {"event": "scheduler_completed", "run_id": run_id})
                break

            ready = [
                worker_id
                for worker_id in get_ready_worker_ids(run, all_contracts)
                if worker_id not in started
            ]
            if not ready and not has_active_workers(run, all_contracts) and has_blocked_workers(run, all_contracts):
                append_audit_event(audit_path, {"event": "scheduler_blocked", "run_id": run_id})
                break

            for worker_id in ready:
                contract = next(c for c in all_contracts if c["worker_id"] == worker_id)
                started.add(worker_id)
                append_audit_event(
                    audit_path,
                    {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id},
                )
                threading.Thread(
                    target=_execute_in_background,
                    args=(run_id, worker_id, contract, audit_path, root, provider),
                    daemon=True,
                ).start()

            time.sleep(5)
    finally:
        with _SCHEDULER_LOCK:
            _ACTIVE_SCHEDULERS.discard(run_id)


class DecisionAgentHandler(SimpleHTTPRequestHandler):
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
        if self._static_path(self.path) is None:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        super().do_GET()

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # POST /api/runs
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

        # POST /api/task-suggestions/refine (with clarification answers)
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

        # POST /api/runs
        if path == "/api/runs":
            try:
                task = self._read_body()
                run = create_run(task, ROOT)
            except Exception as error:
                self._send_json(
                    {"error": {"code": "run_create_failed", "message": str(error)}},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(run, status=HTTPStatus.CREATED)
            return

        # POST /api/runs/:run_id/start
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

        # POST /api/runs/:run_id/architecture/build
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

        # POST /api/runs/:run_id/architecture/approve
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

        # POST /api/runs/:run_id/architecture/reject
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

        # POST /api/runs/:run_id/architecture/generate-contracts
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

        # POST /api/runs/:run_id/schedule
        m = re.fullmatch(r"/api/runs/([^/]+)/schedule", path)
        if m:
            run_id = m.group(1)
            try:
                run = read_run(run_id, ROOT)
                if not run:
                    self._send_json({"error": {"code": "not_found", "message": f"Run {run_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                    return
                if not (run.get("generated_contracts") or run.get("contracts")):
                    self._send_json({"error": {"code": "schedule_failed", "message": "No contracts exist for this run."}}, status=HTTPStatus.BAD_REQUEST)
                    return
                with _SCHEDULER_LOCK:
                    if run_id in _ACTIVE_SCHEDULERS:
                        self._send_json({"run_id": run_id, "status": "already_scheduled"})
                        return
                    _ACTIVE_SCHEDULERS.add(run_id)
                provider = get_provider()
                threading.Thread(
                    target=_run_scheduler,
                    args=(run_id, ROOT, provider),
                    daemon=True,
                ).start()
            except Exception as error:
                self._send_json({"error": {"code": "schedule_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"run_id": run_id, "status": "scheduled"})
            return

        # POST /api/runs/:run_id/agents/:worker_id/message
        m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/message", path)
        if m:
            run_id, worker_id = m.group(1), m.group(2)
            try:
                body = self._read_body()
                run = post_worker_message(run_id, worker_id, body.get("text", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "message_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        # POST /api/runs/:run_id/agents/:worker_id/answer
        m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/answer", path)
        if m:
            run_id, worker_id = m.group(1), m.group(2)
            try:
                body = self._read_body()
                run = answer_worker(run_id, worker_id, body.get("answer", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "answer_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        # POST /api/runs/:run_id/gate/approve
        m = re.fullmatch(r"/api/runs/([^/]+)/gate/approve", path)
        if m:
            run_id = m.group(1)
            try:
                body = self._read_body()
                run = gate_approve(run_id, body.get("note", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "approve_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        # POST /api/runs/:run_id/gate/reject
        m = re.fullmatch(r"/api/runs/([^/]+)/gate/reject", path)
        if m:
            run_id = m.group(1)
            try:
                body = self._read_body()
                run = gate_reject(run_id, body.get("reason", ""), ROOT)
            except Exception as error:
                self._send_json({"error": {"code": "reject_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(run)
            return

        # POST /api/runs/:run_id/agents/:worker_id/execute
        m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/execute", path)
        if m:
            run_id, worker_id = m.group(1), m.group(2)
            try:
                run = read_run(run_id, ROOT)
                if not run:
                    self._send_json({"error": {"code": "not_found", "message": f"Run {run_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                    return
                all_contracts = run.get("contracts", []) + run.get("generated_contracts", [])
                contract = next((c for c in all_contracts if c.get("worker_id") == worker_id), None)
                if not contract:
                    self._send_json({"error": {"code": "not_found", "message": f"Worker {worker_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                    return
                audit_path = ROOT / "data" / "runs" / run_id / "audit.jsonl"
                provider = get_provider()
                thread = threading.Thread(
                    target=_execute_in_background,
                    args=(run_id, worker_id, contract, audit_path, ROOT, provider),
                    daemon=True,
                )
                thread.start()
            except Exception as error:
                self._send_json({"error": {"code": "execute_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"worker_id": worker_id, "status": "started"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

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
