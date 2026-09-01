from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central place for all configuration. Values come from environment
    variables / a .env file (see .env.example). No secrets have defaults
    other than local-dev-friendly ones (Mongo URI, DB name)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "reconcile"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24  # 24h, fine for a take-home demo

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    frontend_url: str = "http://localhost:3000"


settings = Settings()
