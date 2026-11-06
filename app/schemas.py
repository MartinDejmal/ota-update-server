from typing import Any
from pydantic import BaseModel, Field

class Firmware(BaseModel):
    build: int = Field(ge=1); version: str = Field(max_length=64); sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
class Event(BaseModel):
    event_id: str; attempt_id: str; sequence: int = Field(ge=1); status: str; running_firmware: Firmware; occurred_at: str|None=None; error_code: str|None=None
class CheckInIn(BaseModel):
    request_id: str; firmware: Firmware; ota_slot_size: int = Field(gt=0); battery_mv: int|None=None; rssi: int|None=None; reset_reason: str|None=None; events: list[Event] = Field(default_factory=list, max_length=16)
class StartAttempt(BaseModel):
    offer_id: str; from_firmware: Firmware
class EventBatch(BaseModel): events: list[Event] = Field(min_length=1, max_length=16)
class DeviceCreate(BaseModel):
    name: str; product: str; hardware_revision: str; chip: str; ota_layout: str; signing_profile: str; min_ota_battery_mv: int|None=None
class DeploymentCreate(BaseModel): device_id: str; release_id: str
