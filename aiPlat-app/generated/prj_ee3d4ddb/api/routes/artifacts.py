from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.artifact import Artifact
from schemas.artifact import ArtifactResponse
from database import get_db

router = APIRouter()

@router.get("/projects/{project_id}/artifacts", response_model=List[ArtifactResponse])
async def get_artifacts(project_id: str, db: Session = Depends(get_db)):
    artifacts = db.query(Artifact).filter(Artifact.project_id == project_id).all()
    return [ArtifactResponse.from_orm(a) for a in artifacts]