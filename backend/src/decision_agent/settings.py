from dataclasses import dataclass
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
        return self.root / "public"


def get_settings(root: Path | None = None) -> Settings:
    return Settings(root=root or Path.cwd())

