from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./kindle_monitor.db"
    discord_webhook_url: str = ""
    check_interval_hours: int = 12
    request_interval_seconds: int = 2
    request_timeout_seconds: int = 30
    max_retries: int = 3
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    
    google_cloud_project: str = ""
    firestore_database_id: str = "(default)"
    local_wishlist_file: str = "wishlist.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
