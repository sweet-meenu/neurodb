from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from neurodb_core.container import AppContainer
from neurodb_core.controlplane.router import get_container, get_current_user
from neurodb_core.controlplane.store import Project, User
from neurodb_core.dataplane import service
from neurodb_core.dataplane.runtime import ProjectRuntime
from neurodb_core.dataplane.schemas import (
    CollectionInfo,
    DeleteFileResponse,
    FileSummary,
    IngestFileResponse,
    IngestObjectRequest,
    IngestObjectResponse,
    ObjectResponse,
    QueryRequest,
    QueryResponse,
    VersionHistoryEntry,
)

router = APIRouter()

"""Session-authenticated mirror of the data-plane API, mounted under
/api/control/projects/{project_id}/data/... This is what the dashboard
itself calls to browse/query a project's data — it authenticates with the
user's login session rather than the project's API key, so the dashboard
never needs to hold on to (or ask the user to re-paste) a key that's
otherwise only ever shown once at project-creation time. External
applications still use the API-key-authenticated routes in dataplane.router.
"""


def get_owned_project_runtime(
    project_id: str,
    user: User = Depends(get_current_user),
    container: AppContainer = Depends(get_container),
) -> ProjectRuntime:
    project: Project | None = container.control_store.get_project(project_id)
    if project is None or project.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return container.project_runtimes.get_or_create(project.id, project.storage_path)


@router.post("/objects", response_model=IngestObjectResponse, status_code=status.HTTP_201_CREATED)
def create_object(
    body: IngestObjectRequest, runtime: ProjectRuntime = Depends(get_owned_project_runtime)
) -> IngestObjectResponse:
    return service.create_object(runtime, body.collection, body.text, body.metadata)


@router.post("/ingest/text", response_model=IngestFileResponse, status_code=status.HTTP_201_CREATED)
def ingest_text(
    collection: str = Form(...),
    text: str = Form(...),
    runtime: ProjectRuntime = Depends(get_owned_project_runtime),
) -> IngestFileResponse:
    return service.ingest_text(runtime, collection, text)


@router.post("/ingest/file", response_model=IngestFileResponse, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    collection: str = Form(...),
    file: UploadFile = File(...),
    runtime: ProjectRuntime = Depends(get_owned_project_runtime),
) -> IngestFileResponse:
    data = await file.read()
    # process_bytes can run CPU-bound work (e.g. Whisper transcription for
    # audio) that takes seconds; offload to a thread so it doesn't block the
    # single asyncio event loop and freeze every other in-flight request.
    return await run_in_threadpool(service.ingest_file_bytes, runtime, collection, data, file.filename or "upload.txt")


@router.get("/objects/{object_id}", response_model=ObjectResponse)
def get_object(object_id: str, runtime: ProjectRuntime = Depends(get_owned_project_runtime)) -> ObjectResponse:
    return service.get_object(runtime, object_id)


@router.delete("/objects/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_object(object_id: str, runtime: ProjectRuntime = Depends(get_owned_project_runtime)) -> None:
    service.delete_object(runtime, object_id)


@router.get("/collections", response_model=list[CollectionInfo])
def list_collections(runtime: ProjectRuntime = Depends(get_owned_project_runtime)) -> list[CollectionInfo]:
    return service.list_collections(runtime)


@router.get("/collections/{collection}/objects", response_model=list[ObjectResponse])
def list_objects(
    collection: str,
    filename: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    runtime: ProjectRuntime = Depends(get_owned_project_runtime),
) -> list[ObjectResponse]:
    return service.list_objects(runtime, collection, filename=filename, limit=limit, offset=offset)


@router.get("/collections/{collection}/files", response_model=list[FileSummary])
def list_files(
    collection: str, runtime: ProjectRuntime = Depends(get_owned_project_runtime)
) -> list[FileSummary]:
    return service.list_files(runtime, collection)


@router.delete("/collections/{collection}/files", response_model=DeleteFileResponse)
def delete_file(
    collection: str,
    filename: str = Query(...),
    runtime: ProjectRuntime = Depends(get_owned_project_runtime),
) -> DeleteFileResponse:
    return service.delete_file(runtime, collection, filename)


@router.get("/collections/{collection}/files/raw")
def get_raw_file(
    collection: str,
    filename: str = Query(...),
    runtime: ProjectRuntime = Depends(get_owned_project_runtime),
) -> Response:
    data, content_type = service.get_raw_file(runtime, collection, filename)
    return Response(content=data, media_type=content_type)


@router.get("/collections/{collection}/versions", response_model=list[VersionHistoryEntry])
def collection_versions(
    collection: str, runtime: ProjectRuntime = Depends(get_owned_project_runtime)
) -> list[VersionHistoryEntry]:
    return service.collection_versions(runtime)


@router.post("/query", response_model=QueryResponse)
def run_query(body: QueryRequest, runtime: ProjectRuntime = Depends(get_owned_project_runtime)) -> QueryResponse:
    return service.run_query(runtime, body.query)
