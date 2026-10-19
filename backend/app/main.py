import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import admin, analytics, assignments, auth, dependencies, invitations, planning, profile, progress, project_activities, projects, requirements, reviews, skills, tasks, weights
from .db import Base, SessionLocal, engine, migrate_sqlite_project_columns, migrate_sqlite_task_columns, migrate_sqlite_user_columns
from .models import Project, ProjectActivity
from .security import jwt_secret

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    jwt_secret()
    migrate_sqlite_user_columns()
    migrate_sqlite_project_columns()
    migrate_sqlite_task_columns()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        recorded = set(db.scalars(select(ProjectActivity.project_id).where(ProjectActivity.action == "created")).all())
        for project in db.scalars(select(Project)).all():
            if project.id not in recorded:
                db.add(ProjectActivity(
                    project_id=project.id, project_name=project.name,
                    actor_id=project.owner_id, action="created",
                    created_at=project.created_at,
                ))
        db.commit()
    yield


app = FastAPI(title="TaskFlow AI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(requirements.router, prefix="/api")
app.include_router(invitations.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(weights.router, prefix="/api")
app.include_router(dependencies.router, prefix="/api")
app.include_router(planning.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(project_activities.router, prefix="/api")
app.include_router(project_activities.user_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
