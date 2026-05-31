import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/ai_team")
    secret_key: str = os.getenv("SECRET_KEY", "default-secret-key")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"

    class Config:
        env_file = ".env"

settings = Settings()