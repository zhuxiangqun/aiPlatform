from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .database import get_db
from .models import Project, PRD, Architecture
from .schemas import (
    ProjectCreateInput, ProjectCreateOutput,
    PRDGenerateInput, PRDGenerateOutput,
    PRDConfirmInput, PRDConfirmOutput,
    ArchitectureGenerateInput, ArchitectureGenerateOutput
)
from .agents import ProductManagerAgent, SystemArchitectAgent
from datetime import datetime, timezone

project_router = APIRouter()

@project_router.post("/project/create", response_model=ProjectCreateOutput)
async def create_project(input_data: ProjectCreateInput, db: Session = Depends(get_db)):
    project = Project(
        status="created",
        current_phase="init"
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    audit_log = AuditLog(  # noqa: F821
        project_id=project.id,
        phase="init",
        start_time=datetime.now(timezone.utc),
        executor="system",
        artifact_version="1.0"
    )
    db.add(audit_log)
    db.commit()
    
    return ProjectCreateOutput(project_id=project.id, status=project.status)

@project_router.post("/project/{project_id}/prd/generate", response_model=PRDGenerateOutput)
async def generate_prd(project_id: str, input_data: PRDGenerateInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    agent = ProductManagerAgent()
    prd_result = await agent.generate_prd(input_data.conversation_history)
    
    prd = PRD(
        project_id=project_id,
        content=prd_result["content"],
        confirmed=False
    )
    db.add(prd)
    
    project.current_phase = "prd_generated"
    db.commit()
    db.refresh(prd)
    
    return PRDGenerateOutput(
        prd_id=prd.id,
        content=prd.content,
        confirmed=prd.confirmed
    )

@project_router.post("/project/{project_id}/prd/confirm", response_model=PRDConfirmOutput)
async def confirm_prd(project_id: str, input_data: PRDConfirmInput, db: Session = Depends(get_db)):
    prd = db.query(PRD).filter(PRD.id == input_data.prd_id, PRD.project_id == project_id).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    
    prd.confirmed = True
    
    project = db.query(Project).filter(Project.id == project_id).first()
    project.current_phase = "prd_confirmed"
    
    audit_log = AuditLog(  # noqa: F821
        project_id=project_id,
        phase="prd_confirmation",
        start_time=datetime.now(timezone.utc),
        executor="system",
        artifact_version="1.0"
    )
    db.add(audit_log)
    db.commit()
    
    return PRDConfirmOutput(status="confirmed")

@project_router.post("/project/{project_id}/architecture/generate", response_model=ArchitectureGenerateOutput)
async def generate_architecture(project_id: str, input_data: ArchitectureGenerateInput, db: Session = Depends(get_db)):
    prd = db.query(PRD).filter(PRD.id == input_data.prd_id, PRD.project_id == project_id).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    if not prd.confirmed:
        raise HTTPException(status_code=400, detail="PRD must be confirmed before generating architecture")
    
    agent = SystemArchitectAgent()
    arch_result = await agent.generate_architecture(prd.content)
    
    architecture = Architecture(
        project_id=project_id,
        prd_id=input_data.prd_id,
        diagram=arch_result["diagram"],
        description=arch_result["description"],
        confirmed=False
    )
    db.add(architecture)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    project.current_phase = "architecture_generated"
    db.commit()
    db.refresh(architecture)
    
    return ArchitectureGenerateOutput(
        architecture_id=architecture.id,
        diagram=architecture.diagram,
        description=architecture.description,
        confirmed=architecture.confirmed
    )