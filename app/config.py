from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    data_dir: Path = Path("/data")
    public_base_url: str = "http://localhost:8000"
    admin_username: str = "admin"
    offer_ttl_seconds: int = 600
    attempt_idle_timeout_seconds: int = 1800
    max_firmware_bytes: int = 8 * 1024 * 1024

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'ota.sqlite'}"
    @property
    def firmware_dir(self) -> Path:
        return self.data_dir / "firmware"

settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.firmware_dir.mkdir(parents=True, exist_ok=True)
