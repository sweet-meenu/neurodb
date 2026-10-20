from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from neurodb_core.container import AppContainer
from neurodb_core.controlplane.auth import issue_session_token, verify_session_token
from neurodb_core.controlplane.schemas import (
    ConnectionInfoResponse,
    LoginRequest,
    ProjectCreatedResponse,
    ProjectCreateRequest,
    ProjectResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from neurodb_core.controlplane.store import User

router = APIRouter()
_bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    container: AppContainer = Depends(get_container),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing session token")
    user_id = verify_session_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session token")
    user = container.control_store.get_user(user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


def _connection_string(container: AppContainer, project_id: str, api_key: str) -> str:
    return f"neurodb://{project_id}:{api_key}@{container.host}"


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, container: AppContainer = Depends(get_container)) -> UserResponse:
    try:
        user = container.control_store.create_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return UserResponse(id=user.id, email=user.email)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, container: AppContainer = Depends(get_container)) -> TokenResponse:
    user = container.control_store.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return TokenResponse(access_token=issue_session_token(user.id))


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)


@router.post("/projects", response_model=ProjectCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> ProjectCreatedResponse:
    project, api_key = container.control_store.create_project(user.id, body.name)
    return ProjectCreatedResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        api_key_prefix=project.api_key_prefix,
        api_key=api_key,
        connection_string=_connection_string(container, project.id, api_key),
    )


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    user: User = Depends(get_current_user), container: AppContainer = Depends(get_container)
) -> list[ProjectResponse]:
    projects = container.control_store.list_projects(user.id)
    return [
        ProjectResponse(id=p.id, name=p.name, created_at=p.created_at, api_key_prefix=p.api_key_prefix)
        for p in projects
    ]


def _get_owned_project(project_id: str, user: User, container: AppContainer):
    project = container.control_store.get_project(project_id)
    if project is None or project.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> ProjectResponse:
    project = _get_owned_project(project_id, user, container)
    return ProjectResponse(id=project.id, name=project.name, created_at=project.created_at, api_key_prefix=project.api_key_prefix)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> None:
    _get_owned_project(project_id, user, container)
    container.control_store.delete_project(project_id)
    container.project_runtimes.evict(project_id)


@router.post("/projects/{project_id}/rotate-key", response_model=ConnectionInfoResponse)
def rotate_key(
    project_id: str,
    user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> ConnectionInfoResponse:
    project = _get_owned_project(project_id, user, container)
    api_key = container.control_store.rotate_api_key(project_id)
    return ConnectionInfoResponse(
        id=project.id,
        name=project.name,
        connection_string=_connection_string(container, project.id, api_key),
        api_key_prefix=api_key[:12],
    )
