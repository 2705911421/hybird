from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    database_path: Path
    local_token: str = "story-runtime-local"
    busy_timeout_ms: int = 750
    writes_enabled: bool = False

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            database_path=Path(os.getenv("STORY_RUNTIME_DB", "./data/story.db")).expanduser().resolve(),
            local_token=os.getenv("STORY_RUNTIME_TOKEN", "story-runtime-local"),
            busy_timeout_ms=int(os.getenv("STORY_RUNTIME_BUSY_TIMEOUT_MS", "750")),
            writes_enabled=os.getenv("STORY_RUNTIME_ENABLE_WRITES", "0") == "1",
        )
