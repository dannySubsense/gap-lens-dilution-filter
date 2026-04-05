from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API settings
    askedgar_api_key: str = "your-api-key-here"
    fmp_api_key: str = ""
    massive_api_key: str = ""
    askedgar_url: str = "https://eapi.askedgar.io"
    request_timeout: int = 30

    # CORS settings
    cors_origins: list = ["*"]


settings = Settings()
