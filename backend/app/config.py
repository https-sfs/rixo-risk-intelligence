from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Fraud-Spike Investigator"
    cors_origins: str = "http://localhost:5173"
    custom_max_upload_mb: int = 1024
    custom_max_rows: int = 2_000_000
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_mode: str = "test"
    governance_sqlite_path: str = "data/governance.sqlite"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
