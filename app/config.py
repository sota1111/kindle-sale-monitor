from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # When true, register provisional (sample) price-history data at startup so the
    # dashboard can be evaluated without a live data source. Local/dev only.
    seed_sample_data: bool = False

    # Amazon Product Advertising API (PA-API 5.0) — real data source.
    # Credentials are provided at deploy time (Cloud Run secrets).
    paapi_access_key: str = ""
    paapi_secret_key: str = ""
    paapi_partner_tag: str = ""
    paapi_host: str = "webservices.amazon.co.jp"
    paapi_region: str = "us-west-2"
    paapi_marketplace: str = "www.amazon.co.jp"
    # Data source selection: auto | paapi | scrape | browser.
    # "auto" uses PA-API when credentials are configured, otherwise scraping.
    # "browser" drives a logged-in local Chromium (Playwright) over each /dp/<asin>
    # page; it is opt-in only (auto never selects it) and is a local-PC source.
    data_source: str = "auto"

    # Logged-in local browser source (Playwright persistent profile).
    # First login is a one-off headed run (BROWSER_HEADLESS=false); afterwards the
    # saved profile cookies are reused headless.
    browser_profile_dir: str = "~/.kindle-monitor/browser-profile"
    browser_headless: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
