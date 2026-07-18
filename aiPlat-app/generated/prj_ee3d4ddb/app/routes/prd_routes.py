from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, PRD
from app.schemas import PRDGenerateRequest, PRDGenerateResponse, PRDConfirmRequest, PRDConfirmResponse
from app.services.product_manager_agent import ProductManagerAgent

router = APIRouter()
pm_agent = ProductManagerAgent()

@router.post("/generate", response_model=PRDGenerateResponse)
async def generate_prd(
    project_id: str,
    request: PRDGenerateRequest,
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        prd_content = pm_agent.generate_prd(request.conversation_history)
        
        prd = PRD(
            project_id=project_id,
            content=prd_content,
            confirmed=False
        )
        db.add(prd)
        db.commit()
        db.refresh(prd)
        
        return PRDGenerateResponse(
            prd_id=prd.id,
            content=prd.content,
            confirmed=prd.confirmed
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm", response_model=PRDConfirmResponse)
async def confirm_prd(
    project_id: str,
    request: PRDConfirmRequest,
    db: Session = Depends(get_db)
):
    prd = db.query(PRD).filter(
        PRD.id == request.prd_id,
        PRD.project_id == project_id
    ).first()
    
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    
    try:
        confirmed = pm_agent.confirm_prd(prd.content)
        prd.confirmed = confirmed
        db.commit()
        
        return PRDConfirmResponse(status="confirmed" if confirmed else "rejected")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))