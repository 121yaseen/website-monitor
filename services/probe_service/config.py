from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8003
    env: str = "dev"
    db_connection_string: str = "probe_results.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="PROBE_"
    )


settings = Settings()
