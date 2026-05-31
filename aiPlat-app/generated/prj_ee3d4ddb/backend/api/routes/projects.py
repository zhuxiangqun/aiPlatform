from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.models.project import Project
from backend.schemas.project import ProjectCreate, ProjectResponse, RoleAssignRequest, StatusResponse
from backend.services.workflow import WorkflowEngine
from backend.database import get_db

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.post("", response_model=StatusResponse)
async def create_project(project_data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=project_data.name, requirements=project_data.requirements)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"status": "created", "project_id": project.id}

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/{project_id}/roles", response_model=StatusResponse)
async def assign_roles(project_id: str, role_data: RoleAssignRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workflow = WorkflowEngine(db)
    result = workflow.assign_roles(project_id, role_data.roles)
    return {"status": result}

@router.post("/{project_id}/confirm-prd", response_model=StatusResponse)
async def confirm_prd(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workflow = WorkflowEngine(db)
    result = workflow.confirm_prd(project_id)
    return {"status": result}