from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import zoneinfo


class Settings(BaseSettings):
    # BLE
    esp32_mac_address: str = Field(default="", description="MAC address of the ESP32 device")

    # Calendar provider: "microsoft" or "google"
    calendar_provider: str = Field(default="microsoft")

    # Microsoft Graph — client ID and tenant come from docker-compose.yml environment block
    ms_graph_client_id: str = Field(default="")
    # Device-code flow is NOT supported on /common — work/school accounts require /organizations
    ms_graph_tenant_id: str = Field(default="organizations")

    # Google Calendar — client ID from docker-compose.yml; secret from .env only (never commit)
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")

    # Schedule
    business_hours_start: float = Field(default=9.0, description="Business hours start (fractional 24h, e.g. 8.5 = 8:30 AM)")
    business_hours_end: float = Field(default=17.0, description="Business hours end (fractional 24h, e.g. 17.5 = 5:30 PM)")
    business_days: list[int] = Field(default=[0, 1, 2, 3, 4], description="0=Mon, 6=Sun")
    timezone: str = Field(default="America/New_York")

    # Polling
    graph_poll_interval_seconds: int = Field(default=60)
    ble_reconnect_interval_seconds: int = Field(default=10)

    # Override
    default_override_timeout_minutes: int = Field(default=60)

    # Paths
    data_dir: str = Field(default="/app/data")

    # Display
    default_brightness: int = Field(default=128)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def tz(self):
        return zoneinfo.ZoneInfo(self.timezone)


settings = Settings()
