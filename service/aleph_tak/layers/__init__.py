"""Capture layers. Each module exposes run(ctx) -> LayerResult and is resumable: anything already
downloaded into ctx.work is reused, so re-running a failed or interrupted job only fetches gaps."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    job_dir: Path
    name: str                 # file-name stem used inside the package
    polygon: list             # [(lat, lon), ...] — Aleph convention
    options: dict             # validated per-job options (zooms, DTED level, formats)
    settings: dict            # service settings (sources, tokens, limits)
    client: object            # core.common.Client bound to this job's cancel flag
    progress: object          # progress(phase, done=0, total=None, unit=None)

    def work(self, layer):
        path = self.job_dir / "work" / layer
        path.mkdir(parents=True, exist_ok=True)
        return path

    def output(self):
        path = self.job_dir / "out"
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass
class LayerResult:
    entries: list = field(default_factory=list)   # formats.datapackage.Entry
    attribution: str = ""
    stats: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    web: dict = field(default_factory=dict)       # what the service can serve to CloudTAK
