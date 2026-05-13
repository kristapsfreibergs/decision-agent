from __future__ import annotations

import re
import threading
from http import HTTPStatus

from decision_agent.modules.runs.service import answer_worker, gate_approve, gate_reject, post_worker_message, read_run
from decision_agent.modules.runs.state import PHASE_GATE_APPROVED, PHASE_GATE_REJECTED
from decision_agent.server_runtime import ROOT, _ACTIVE_SCHEDULERS, _SCHEDULER_LOCK, _can_execute_contract, _execute_in_background, _run_scheduler
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.registry import get_provider


def handle_worker_post(handler, path: str) -> bool:
    m = re.fullmatch(r"/api/runs/([^/]+)/schedule", path)
    if m:
        run_id = m.group(1)
        try:
            run = read_run(run_id, ROOT)
            if not run:
                handler._send_json({"error": {"code": "not_found", "message": f"Run {run_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                return True
            if not (run.get("generated_contracts") or run.get("contracts")):
                handler._send_json({"error": {"code": "schedule_failed", "message": "No contracts exist for this run."}}, status=HTTPStatus.BAD_REQUEST)
                return True
            with _SCHEDULER_LOCK:
                if run_id in _ACTIVE_SCHEDULERS:
                    handler._send_json({"run_id": run_id, "status": "already_scheduled"})
                    return True
                _ACTIVE_SCHEDULERS.add(run_id)
            provider = get_provider(run.get("provider_override"))
            threading.Thread(
                target=_run_scheduler,
                args=(run_id, ROOT, provider),
                daemon=True,
            ).start()
        except Exception as error:
            handler._send_json({"error": {"code": "schedule_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json({"run_id": run_id, "status": "scheduled"})
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/message", path)
    if m:
        run_id, worker_id = m.group(1), m.group(2)
        try:
            body = handler._read_body()
            run = post_worker_message(run_id, worker_id, body.get("text", ""), ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "message_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/answer", path)
    if m:
        run_id, worker_id = m.group(1), m.group(2)
        try:
            body = handler._read_body()
            run = answer_worker(run_id, worker_id, body.get("answer", ""), ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "answer_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/gate/approve", path)
    if m:
        run_id = m.group(1)
        try:
            body = handler._read_body()
            run = gate_approve(run_id, body.get("note", ""), ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "approve_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/gate/reject", path)
    if m:
        run_id = m.group(1)
        try:
            body = handler._read_body()
            run = gate_reject(run_id, body.get("reason", ""), ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "reject_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/agents/([^/]+)/execute", path)
    if m:
        run_id, worker_id = m.group(1), m.group(2)
        try:
            run = read_run(run_id, ROOT)
            if not run:
                handler._send_json({"error": {"code": "not_found", "message": f"Run {run_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                return True
            all_contracts = run.get("generated_contracts") or run.get("contracts", [])
            contract = next((c for c in all_contracts if c.get("worker_id") == worker_id), None)
            if not contract:
                handler._send_json({"error": {"code": "not_found", "message": f"Worker {worker_id} not found"}}, status=HTTPStatus.NOT_FOUND)
                return True
            allowed, message = _can_execute_contract(run, contract)
            if not allowed:
                handler._send_json(
                    {"error": {"code": "gate_not_cleared", "message": message}},
                    status=HTTPStatus.FORBIDDEN,
                )
                return True
            audit_path = ROOT / "data" / "runs" / run_id / "audit.jsonl"
            provider = get_provider(run.get("provider_override"))
            thread = threading.Thread(
                target=_execute_in_background,
                args=(run_id, worker_id, contract, audit_path, ROOT, provider),
                daemon=True,
            )
            thread.start()
        except Exception as error:
            handler._send_json({"error": {"code": "execute_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json({"worker_id": worker_id, "status": "started"})
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/phase-gate/approve", path)
    if m:
        run_id = m.group(1)
        try:
            body = handler._read_body()
            phase_id = body.get("phase_id", "")
            audit_path = ROOT / "data" / "runs" / run_id / "audit.jsonl"
            append_audit_event(
                audit_path,
                {"event": PHASE_GATE_APPROVED, "run_id": run_id, "phase_id": phase_id},
            )
            run = read_run(run_id, ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "phase_gate_approve_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    m = re.fullmatch(r"/api/runs/([^/]+)/phase-gate/reject", path)
    if m:
        run_id = m.group(1)
        try:
            body = handler._read_body()
            phase_id = body.get("phase_id", "")
            reason = body.get("reason", "")
            audit_path = ROOT / "data" / "runs" / run_id / "audit.jsonl"
            append_audit_event(
                audit_path,
                {"event": PHASE_GATE_REJECTED, "run_id": run_id, "phase_id": phase_id, "reason": reason},
            )
            run = read_run(run_id, ROOT)
        except Exception as error:
            handler._send_json({"error": {"code": "phase_gate_reject_failed", "message": str(error)}}, status=HTTPStatus.BAD_REQUEST)
            return True
        handler._send_json(run)
        return True

    return False
