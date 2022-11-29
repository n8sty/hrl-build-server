import asyncio
import os
import sqlite3
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from structlog import get_logger

from . import interface
from .config import Config

_logger = get_logger(__name__)


def get_db():
    sqlite3.register_adapter(UUID, lambda uid: uid.hex)
    db = sqlite3.connect("db.sqlite")
    db.row_factory = sqlite3.Row
    return db


def db():
    db = get_db()
    try:
        yield db
    finally:
        db.close()


def build(*, path: Path, build_id: UUID) -> None:
    logger = _logger.new(path=path)
    logger.info("Running build")
    conn = get_db()
    conn.execute(
        "UPDATE build SET status = ? WHERE id = ?",
        (interface.BuildStatus.building, build_id),
    )

    pull = subprocess.Popen(("git", "-C", path, "pull"), stderr=subprocess.PIPE)
    conn.commit()

    try:
        pull_exit_code = pull.wait(60)
    except subprocess.TimeoutExpired:
        logger.exception("Pulling project timeout out")
        conn.execute(
            "UPDATE build SET status = ? WHERE id = ?",
            (interface.BuildStatus.failure, build_id),
        )
        conn.commit()
        return
    if pull_exit_code != 0:
        logger.exception("Pulling project failed", exit_code=pull_exit_code)
        conn.execute(
            "UPDATE build SET status = ? WHERE id = ?",
            (interface.BuildStatus.failure, build_id),
        )
        conn.commit()
        return

    try:
        git_rev = subprocess.run(
            ("git", "-C", path, "rev-parse", "HEAD"), stdout=subprocess.PIPE, check=True
        )
    except subprocess.CalledProcessError:
        conn.execute(
            "UPDATE build SET status = ? WHERE id = ?",
            (interface.BuildStatus.failure, build_id),
        )
        return
    commit_sha = git_rev.stdout.decode().strip()
    conn.execute(
        "UPDATE build SET commit_sha = ? WHERE id = ?",
        (commit_sha, build_id),
    )
    conn.commit()

    make = subprocess.Popen(("make", "-C", path), stderr=subprocess.PIPE)

    try:
        make_exit_code = make.wait(900)
    except subprocess.TimeoutExpired:
        conn.execute(
            "UPDATE build SET status = ? WHERE id = ?",
            (interface.BuildStatus.failure, build_id),
        )
        conn.commit()
        return
    if make_exit_code != 0:
        conn.execute(
            "UPDATE build SET status = ? WHERE id = ?",
            (interface.BuildStatus.failure, build_id),
        )
        conn.commit()
        return
    artifact = max(
        (p for p in path.iterdir() if p.is_file()),
        key=lambda x: os.path.getctime(x),
    )
    conn.execute(
        "UPDATE build SET artifact = ?, status = ?, finished = datetime() WHERE id = ?",
        (
            sqlite3.Binary(artifact.read_bytes()),
            interface.BuildStatus.success,
            build_id,
        ),
    )
    conn.commit()


def create() -> FastAPI:
    logger = _logger.new()
    config = Config()
    app = FastAPI(
        title="HRL Build Server",
        version="0.0.1",
    )

    scheduler = AsyncIOScheduler(
        {
            "apscheduler.jobstores.default": {
                "type": "sqlalchemy",
                "url": f"sqlite:///{config.db}",
            },
            "apscheduler.executors.default": {
                "class": "apscheduler.executors.pool:ThreadPoolExecutor",
                "max_workers": "5",
            },
        }
    )

    @app.on_event("startup")
    async def startup():
        if not config.data_dir.exists():
            config.data_dir.mkdir(parents=True)
        scheduler.start()

    program_router = APIRouter(prefix="/program")

    @program_router.post("/register", response_model=interface.Program)
    def register_program(
        params: interface.CreateProgram, db: sqlite3.Connection = Depends(db)
    ):
        uid = uuid4()

        clone = subprocess.Popen(
            ("git", "clone", params.source, config.data_dir / params.name),
            stderr=subprocess.PIPE,
        )
        try:
            clone_exit_code = clone.wait(timeout=params.clone_timeout_seconds)
        except subprocess.TimeoutExpired as clone_timeout_exc:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "Failed cloning Git repository",
                    "detail": clone_timeout_exc.args,
                },
            )
        if clone_exit_code != 0:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "Failed cloning Git repository",
                    "detail": clone.stderr.read().decode(),
                },
            )

        cursor = db.execute(
            """
                INSERT INTO program (id, name, source, build_schedule)
                VALUES (?, ?, ?, ?)
                RETURNING *
            """,
            (uid, params.name, params.source, params.build_schedule),
        )
        data = cursor.fetchone()
        db.commit()

        if params.build_schedule == "@hourly":
            scheduler.add_job(
                build,
                kwargs=dict(path=config.data_dir / params.name, build_id=uid),
                trigger="interval",
                hourly=1,
            )

        return {**data}

    @program_router.post("/build")
    def build_program(
        params: interface.TriggerBuild,
        request: Request,
        db: sqlite3.Connection = Depends(db),
    ):
        uid = uuid4()
        db.execute(
            """
                INSERT INTO build (id, program_id, status)
                VALUES (?, (SELECT id FROM program WHERE name = ?), ?)
            """,
            (uid, params.program_name, interface.BuildStatus.queued),
        )
        db.commit()

        scheduler.add_job(
            build,
            kwargs=dict(path=config.data_dir / params.program_name, build_id=uid),
        )

        return {"build_id": uid, "program_name": params.program_name}

    @program_router.get("/build/{build_id}")
    def get_build(
        build_id: UUID, db: sqlite3.Connection = Depends(db)
    ):
        cursor = db.execute(
            """
                SELECT
                    build.id,
                    program.name,
                    build.commit_sha,
                    build.status,
                    build.created,
                    build.finished
                FROM build
                INNER JOIN program ON program.id = build.program_id
                WHERE build.id = ?
            """,
            (build_id,),
        )
        build = cursor.fetchone()
        return build

    @app.exception_handler(sqlite3.IntegrityError)
    def db_integrity_error_handler(request: Request, exc: sqlite3.IntegrityError):
        return JSONResponse(
            status_code=400,
            content={
                "message": "Command failed due to some sort of data constraint",
                "detail": exc.args,
            },
        )

    app.include_router(program_router)

    return app
