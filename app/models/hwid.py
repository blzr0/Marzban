from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class SubscriptionLogStatus(str, Enum):
    ok = "ok"
    expired = "expired"
    revoked = "revoked"
    hwid_limit_exceeded = "hwid_limit_exceeded"
    hwid_missing = "hwid_missing"


@dataclass
class SubscriptionRequest:
    """Who fetched a subscription: device headers, client, IP and the domain/path used."""
    hwid: Optional[str] = None
    device_os: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    request_path: Optional[str] = None


class UserHWIDResponse(BaseModel):
    id: int
    hwid: str
    device_os: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserHWIDsResponse(BaseModel):
    hwids: List[UserHWIDResponse]
    hwid_limit: int


class SubscriptionLogResponse(BaseModel):
    id: int
    username: str
    status: SubscriptionLogStatus
    hwid: Optional[str] = None
    device_os: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    request_path: Optional[str] = None
    count: int
    created_at: datetime
    updated_at: datetime


class SubscriptionLogsResponse(BaseModel):
    logs: List[SubscriptionLogResponse]
    total: int
