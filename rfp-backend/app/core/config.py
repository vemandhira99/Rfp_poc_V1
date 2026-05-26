from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Azure OpenAI (if using Azure)
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4o-mini"
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    
    AI_PROVIDER_PRIMARY: str = "gemini"
    AI_PROVIDER_FALLBACK: str = "openai" # Can be 'openai' or 'azure'
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 50

    class Config:
        env_file = ".env"

settings = Settings()