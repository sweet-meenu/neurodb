from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from neurodb_core.controlplane.auth import generate_api_key, hash_api_key, hash_password, verify_password
from neurodb_core.controlplane.db import Database


@dataclass
class User:
    id: str
    email: str


@dataclass
class Project:
    id: str
    owner_user_id: str
    name: str
    storage_path: str
    created_at: float
    api_key_prefix: str


class ControlPlaneStore:
    """Users, projects, and API-key bookkeeping. Each project provisioned
    here maps 1:1 to an isolated on-disk StorageEngine root — creating a
    project is what "provisioning a database instance" means in NeuroDB.
    """

    def __init__(self, db: Database, data_root: Path):
        self.db = db
        self.data_root = Path(data_root)

    # -- users ------------------------------------------------------------

    def create_user(self, email: str, password: str) -> User:
        if self.db.query_one("SELECT id FROM users WHERE email = ?", (email,)) is not None:
            raise ValueError("email already registered")
        user_id = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, hash_password(password), time.time()),
        )
        return User(id=user_id, email=email)

    def authenticate(self, email: str, password: str) -> User | None:
        row = self.db.query_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return User(id=row["id"], email=row["email"])

    def get_user(self, user_id: str) -> User | None:
        row = self.db.query_one("SELECT id, email FROM users WHERE id = ?", (user_id,))
        return User(id=row["id"], email=row["email"]) if row else None

    # -- projects -----------------------------------------------------------

    def create_project(self, owner_user_id: str, name: str) -> tuple[Project, str]:
        project_id = uuid.uuid4().hex
        api_key = generate_api_key()
        storage_path = str(self.data_root / project_id)
        now = time.time()
        self.db.execute(
            "INSERT INTO projects "
            "(id, owner_user_id, name, api_key_hash, api_key_prefix, storage_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, owner_user_id, name, hash_api_key(api_key), api_key[:12], storage_path, now),
        )
        project = Project(
            id=project_id,
            owner_user_id=owner_user_id,
            name=name,
            storage_path=storage_path,
            created_at=now,
            api_key_prefix=api_key[:12],
        )
        return project, api_key

    def list_projects(self, owner_user_id: str) -> list[Project]:
        rows = self.db.query_all(
            "SELECT id, owner_user_id, name, storage_path, created_at, api_key_prefix "
            "FROM projects WHERE owner_user_id = ? ORDER BY created_at DESC",
            (owner_user_id,),
        )
        return [Project(**dict(row)) for row in rows]

    def get_project(self, project_id: str) -> Project | None:
        row = self.db.query_one(
            "SELECT id, owner_user_id, name, storage_path, created_at, api_key_prefix "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        return Project(**dict(row)) if row else None

    def delete_project(self, project_id: str) -> None:
        self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def rotate_api_key(self, project_id: str) -> str:
        api_key = generate_api_key()
        self.db.execute(
            "UPDATE projects SET api_key_hash = ?, api_key_prefix = ? WHERE id = ?",
            (hash_api_key(api_key), api_key[:12], project_id),
        )
        return api_key

    def get_project_by_api_key(self, api_key: str) -> Project | None:
        row = self.db.query_one(
            "SELECT id, owner_user_id, name, storage_path, created_at, api_key_prefix "
            "FROM projects WHERE api_key_hash = ?",
            (hash_api_key(api_key),),
        )
        return Project(**dict(row)) if row else None
