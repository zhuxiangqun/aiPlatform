from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.project import Project
from services.bug_fixer import BugFixer
from database import get_db

router = APIRouter()

@router.post("/{project_id}/bugs")
async def fix_bugs(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = BugFixer(db)
    bug_id = await service.fix(project_id)
    return {"bug_id": bug_id}