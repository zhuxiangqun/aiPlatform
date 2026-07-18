from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, PRD, Architecture
from app.schemas import ArchitectureGenerateRequest, ArchitectureGenerateResponse
from app.services.system_architect_agent import SystemArchitectAgent

router = APIRouter()
arch_agent = SystemArchitectAgent()

@router.post("/generate", response_model=ArchitectureGenerateResponse)
async def generate_architecture(
    project_id: str,
    request: ArchitectureGenerateRequest,
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    prd = db.query(PRD).filter(PRD.id == request.prd_id).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    
    try:
        arch_data = arch_agent.generate_architecture(prd.content)
        
        architecture = Architecture(
            project_id=project_id,
            prd_id=request.prd_id,
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))