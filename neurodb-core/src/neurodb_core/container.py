from __future__ import annotations

from pathlib import Path

from neurodb_core.controlplane.db import Database
from neurodb_core.controlplane.store import ControlPlaneStore
from neurodb_core.dataplane.runtime import ProjectRuntimeCache


class AppContainer:
    """Process-wide dependencies wired together once at app startup and
    attached to app.state, rather than module-level globals — so tests can
    spin up independent app instances against independent temp directories.
    """

    def __init__(self, data_root: Path, *, host: str = "localhost:8000"):
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.host = host
        self.db = Database(self.data_root / "controlplane.sqlite3")
        self.control_store = ControlPlaneStore(self.db, self.data_root / "projects")
        self.project_runtimes = ProjectRuntimeCache()
