#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from decision_agent.modules.architectures.registry import list_architectures
from decision_agent.modules.contracts.validator import validate_contract_file
from decision_agent.modules.runs.service import create_run


def print_usage() -> None:
    print(
        """decision-agent

Commands:
  list
  run <task.json>
  benchmark-config <config.json>
  validate-contract <contract.json>

Examples:
  python3 -m decision_agent.cli list
  python3 -m decision_agent.cli run examples/build-decision-agent.json
  python3 -m decision_agent.cli benchmark-config configs/benchmarks/procurement-layer-ablation.json
"""
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else None

    if not command or command in {"-h", "--help"}:
        print_usage()
        return 0

    if command == "list":
        for architecture in list_architectures():
            workers = ", ".join(worker["worker_id"] for worker in architecture["workers"])
            print(f"{architecture['id']} ({architecture['decision_type']})")
            print(f"  risk: {architecture['risk_level']}")
            print(f"  workers: {workers}")
        return 0

    if command == "run":
        if len(args) < 2:
            raise ValueError("Missing task JSON path.")
        task_path = Path(args[1]).resolve()
        task = json.loads(task_path.read_text(encoding="utf-8"))
        run = create_run(task, root=Path.cwd())
        print(f"Decision type: {run['decision_type']}")
        print(f"Architecture: {run['architecture_id']}")
        print(f"Risk: {run['risk_level']}")
        print(f"Run ID: {run['run_id']}")
        print(f"Run folder: {run['run_dir']}")
        print("")
        print("Worker contracts:")
        for contract in run["contracts"]:
            print(f"- {contract['worker_id']}: {contract['goal']}")
        print("")
        print(f"Status: {run['status']}")
        return 0

    if command == "benchmark-config":
        if len(args) < 2:
            raise ValueError("Missing benchmark config JSON path.")
        from decision_agent.modules.evaluation.config_runner import run_benchmark_config

        config_path = Path(args[1]).resolve()
        state = run_benchmark_config(config_path, root=Path.cwd())
        print(f"Benchmark: {state['benchmark_id']}")
        print(f"Status: {state['status']}")
        print(f"Completed: {state['completed_runs']}/{state['total_runs']}")
        out_dir = Path.cwd() / "data" / "benchmarks" / state["benchmark_id"]
        print(f"Results: {out_dir / 'results.csv'}")
        print(f"Summary: {out_dir / 'summary.json'}")
        return 0

    if command == "validate-contract":
        if len(args) < 2:
            raise ValueError("Missing contract JSON path.")
        result = validate_contract_file(Path(args[1]).resolve())
        if result["valid"]:
            print("Contract valid.")
            return 0
        print("Contract invalid:", file=sys.stderr)
        for issue in result["issues"]:
            print(f"- {issue}", file=sys.stderr)
        return 1

    raise ValueError(f"Unknown command: {command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
