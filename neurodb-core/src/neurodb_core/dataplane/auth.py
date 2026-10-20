from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from neurodb_core.container import AppContainer
from neurodb_core.controlplane.store import Project
from neurodb_core.dataplane.runtime import ProjectRuntime


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_current_project(request: Request, container: AppContainer = Depends(get_container)) -> Project:
    api_key = request.headers.get("X-NeuroDB-Api-Key")
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[len("Bearer ") :]
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key")
    project = container.control_store.get_project_by_api_key(api_key)
    if project is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
    return project


def get_project_runtime(
    project: Project = Depends(get_current_project),
    container: AppContainer = Depends(get_container),
) -> ProjectRuntime:
    return container.project_runtimes.get_or_create(project.id, project.storage_path)
