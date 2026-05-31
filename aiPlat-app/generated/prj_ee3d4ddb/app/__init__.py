from fastapi import FastAPI
from app.database import engine, Base
from app.routes import router

app = FastAPI(title="Multi-Agent Software Development Platform")

Base.metadata.create_all(bind=engine)

app.include_router(router)