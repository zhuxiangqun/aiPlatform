from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.models.artifact import Artifact
from backend.schemas.artifact import ArtifactResponse
from backend.database import get_db

router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])

@router.get("", response_model=List[ArtifactResponse])
async def list_artifacts(project_id: str, db: Session = Depends(get_db)):
    artifacts = db.query(Artifact).filter(Artifact.project_id == project_id).all()
    return artifacts

@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(project_id: str, artifact_id: str, db: Session = Depends(get_db)):
    artifact = db.query(Artifact).filter(Artifact.id == artifact_id, Artifact.project_id == project_id).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact