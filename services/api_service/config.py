from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8001
    db_connection_string: str = "probe_results.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="API_", extra="ignore"
    )


settings = Settings()
