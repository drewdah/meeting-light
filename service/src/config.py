from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import zoneinfo


class Settings(BaseSettings):
    # BLE
    esp32_mac_address: str = Field(default="", description="MAC address of the ESP32 device")

    # Calendar provider: "microsoft" or "google"
    calendar_provider: str = Field(default="microsoft")

    # Microsoft Graph
    ms_graph_client_id: str = Field(default="")
    ms_graph_tenant_id: str = Field(default="common")

    # Google Calendar
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")

    # Schedule
    business_hours_start: int = Field(default=9, description="Business hours start (24h)")
    business_hours_end: int = Field(default=17, description="Business hours end (24h)")
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
