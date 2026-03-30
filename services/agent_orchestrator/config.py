from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8004
    host: str = "0.0.0.0"

    # LLM
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    llm_is_azure: bool = False  # if True, sends api-key header instead of Bearer

    # TTS
    tts_provider: str = "azure"
    azure_tts_key: str = ""
    azure_tts_region: str = "eastus"
    azure_tts_voice: str = "en-US-AvaMultilingualNeural"

    # Session
    max_context_turns: int = 8
    system_prompt: str = "You are a helpful voice assistant. Be concise and conversational."

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AGENT_",
        extra="ignore",
    )


settings = Settings()
