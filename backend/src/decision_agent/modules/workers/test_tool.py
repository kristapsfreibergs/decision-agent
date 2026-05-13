from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

def _run_tests(command: str, project_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    allowed_commands = {
        "npm test": (["npm", "test"], {}),
        "python3 -m unittest discover backend/tests": (
            ["python3", "-m", "unittest", "discover", "backend/tests"],
            {"PYTHONPATH": "backend/src"},
        ),
        "PYTHONPATH=backend/src python3 -m unittest discover backend/tests": (
            ["python3", "-m", "unittest", "discover", "backend/tests"],
            {"PYTHONPATH": "backend/src"},
        ),
    }
    if command not in allowed_commands:
        return subprocess.CompletedProcess(
            args=shlex.split(command),
            returncode=2,
            stdout="",
            stderr=(
                "ERROR: run_tests command is not approved. "
                f"Allowed commands: {', '.join(sorted(allowed_commands))}"
            ),
        )

    args, extra_env = allowed_commands[command]
    env.update(extra_env)
    return subprocess.run(
        args,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
