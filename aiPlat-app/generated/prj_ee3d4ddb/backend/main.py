from fastapi import FastAPI
from backend.api.routes import projects_router, artifacts_router, test_results_router, audit_logs_router
from backend.database import engine
from backend.models.project import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Software Team API", version="1.0.0")

app.include_router(projects_router)
app.include_router(artifacts_router)
app.include_router(test_results_router)
app.include_router(audit_logs_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}