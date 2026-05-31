from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, PRD, Architecture
from app.schemas import (
    ProjectCreate, ProjectCreateResponse,
    PRDGenerateInput, PRDGenerateResponse,
    PRDConfirmInput, PRDConfirmResponse,
    ArchitectureGenerateInput, ArchitectureGenerateResponse
)
from app.services.agent_manager import ProductManagerAgent, SystemArchitectAgent
from app.services.llm_service import LLMService
from datetime import datetime
import uuid

router = APIRouter(prefix="/project")
llm_service = LLMService()
pm_agent = ProductManagerAgent(llm_service)
arch_agent = SystemArchitectAgent(llm_service)

@router.post("/create", response_model=ProjectCreateResponse)
async def create_project(input_data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        description=input_data.description,
        team_members=input_data.team_members,
        status="created",
        current_phase="prd"
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectCreateResponse(project_id=project.id, status=project.status)

@router.post("/{project_id}/prd/generate", response_model=PRDGenerateResponse)
async def generate_prd(project_id: str, input_data: PRDGenerateInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    content = await pm_agent.generate_prd(input_data.conversation_history)
    prd = PRD(project_id=project_id, content=content, confirmed=False)
    db.add(prd)
    project.current_phase = "prd"
    db.commit()
    db.refresh(prd)
    return PRDGenerateResponse(prd_id=prd.id, content=prd.content, confirmed=prd.confirmed)

@router.post("/{project_id}/prd/confirm", response_model=PRDConfirmResponse)
async def confirm_prd(project_id: str, input_data: PRDConfirmInput, db: Session = Depends(get_db)):
    prd = db.query(PRD).filter(PRD.id == input_data.prd_id, PRD.project_id == project_id).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    
    prd.confirmed = True
    project = db.query(Project).filter(Project.id == project_id).first()
    project.current_phase = "architecture"
    db.commit()
    return PRDConfirmResponse(status="confirmed")

@router.post("/{project_id}/architecture/generate", response_model=ArchitectureGenerateResponse)
async def generate_architecture(project_id: str, input_data: ArchitectureGenerateInput, db: Session = Depends(get_db)):
    prd = db.query(PRD).filter(PRD.id == input_data.prd_id, PRD.project_id == project_id).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    
    arch_data = await arch_agent.generate_architecture(prd.content)
    architecture = Architecture(
        project_id=project_id,
        prd_id=prd.id,
        diagram=arch_data["diagram"],
        description=arch_data["description"],
        confirmed=False
    )
    db.add(architecture)
    db.commit()
    db.refresh(architecture)
    return ArchitectureGenerateResponse(
        architecture_id=architecture.id,
        diagram=architecture.diagram,
        description=architecture.description,
        confirmed=architecture.confirmed
    )