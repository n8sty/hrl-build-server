from enum import Enum
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, validator


class BuildStatus(str, Enum):
    queued = "queued"
    building = "building"
    success = "success"
    failure = "failure"


_acceptable_schedules = ("@hourly",)


class CreateProgram(BaseModel):
    name: str
    source: str
    build_schedule: str | None
    clone_timeout_seconds: int = 15

    @validator("build_schedule")
    def allowed_build_schedules(cls, v):
        if not v:
            return v
        if v not in _acceptable_schedules:
            raise ValueError(f"Only acceptable schedules are: {_acceptable_schedules}")
        return v


class Program(CreateProgram):
    id: UUID


class TriggerBuild(BaseModel):
    program_name: str


class BuildLocation(BaseModel):
    id: UUID
    build_url: AnyHttpUrl


class Build(BaseModel):
    id: UUID
    program_id: UUID
    commit_sha: str
    status: BuildStatus
    build_url: AnyHttpUrl


class BuildSchedule(BaseModel):
    program_id: UUID
    cron: str
