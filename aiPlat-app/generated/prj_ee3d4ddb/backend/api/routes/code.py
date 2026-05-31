from fastapi import APIRouter, HTTPException
from services.code_generator import CodeGenerator
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@router.post("/api/projects/{project_id}/code")
def generate_code(project_id: str):
    db = SessionLocal()
    try:
        generator = CodeGenerator(db)
        code_id = generator.generate_code(project_id)
        return {"code_id": code_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()