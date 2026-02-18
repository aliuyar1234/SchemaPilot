"""Pydantic request/response schemas for control-plane endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile: str = Field(default="starter")
    security_baseline: str = Field(default="standard")


class WorkspaceResponse(BaseModel):
    workspace_id: str
    name: str
    profile: str
    security_baseline: str


class SourceCreateRequest(BaseModel):
    source_type: str
    scope: dict[str, object]
    display_name: str
    credentials: dict[str, str] | None = None


class SourceResponse(BaseModel):
    source_id: str
    workspace_id: str
    source_type: str
    scope: dict[str, object]
    display_name: str
    status: str
    credentials_ref: str | None = None


class RunCreateRequest(BaseModel):
    run_type: str


class RunResponse(BaseModel):
    run_id: str
    workspace_id: str
    run_type: str
    status: str


class RecommendationCreateRequest(BaseModel):
    intent: dict[str, object] = Field(default_factory=dict)


class ErrorInner(BaseModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorInner
