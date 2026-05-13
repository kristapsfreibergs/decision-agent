from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    host: str = "127.0.0.1"
    port: int = 4177

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def public_dir(self) -> Path:
        return self.root / "archive" / "public"


def get_settings(root: Path | None = None) -> Settings:
    resolved_root = root or Path.cwd()
    load_env_file(resolved_root / ".env")
    return Settings(root=resolved_root)


def load_env_file(path: Path) -> None:
    """Load simple KEY=value entries into the process environment."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
