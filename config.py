from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "AcentoPartners Email Classifier"
    debug: bool = True
    log_level: str = "INFO"

    # Microsoft Graph API
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    outlook_mailbox: str = ""
    outlook_poll_interval: int = 60

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"

    # Clasificador LLM opcional (reglas primero, LLM como apoyo)
    use_llm_classifier: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"  # 3b: ~3-4x mas rapido que 8b en CPU
    ollama_timeout: float = 300.0  # 8B CPU-only: cold-start puede pasar 200s; 45s daba ReadTimeout

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"dev", "development"}:
                return True
        return value


settings = Settings()
