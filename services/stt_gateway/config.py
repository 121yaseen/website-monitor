from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    port:int = 8002
    host:str = "0.0.0.0"
    provider:str = "azure"
    endpoint:str = "https://eastus.api.cognitive.microsoft.com/"
    subscription_key:str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="STT_", extra="ignore",
    )

settings = Settings()