from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.project import Project
from models.project_role import ProjectRole
from schemas.project import ProjectCreate, ProjectResponse, ProjectRoleInput, ConfirmPRDResponse
from services.workflow import WorkflowEngine
from database import get_db

router = APIRouter()

@router.post("/projects", response_model=dict)
async def create_project(project_data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=project_data.name, requirements=project_data.requirements)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"project_id": str(project.id), "status": project.status}

@router.get("/projects/{project_id}", response_model=dict)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": ProjectResponse.from_orm(project)}

@router.post("/projects/{project_id}/roles", response_model=dict)
async def assign_roles(project_id: str, role_input: ProjectRoleInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for role_data in role_input.roles:
        project_role = ProjectRole(
            project_id=project_id,
            role_name=role_data["role_name"],
            user_id=role_data["user_id"]
        )
        db.add(project_role)
    db.commit()
    return {"status": "roles assigned"}

@router.post("/projects/{project_id}/confirm-prd", response_model=dict)
async def confirm_prd(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    engine = WorkflowEngine(db)
    result = engine.confirm_prd(project_id)
    return {"status": result}