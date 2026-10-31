from typing import List, Optional, Union

from pydantic import BaseModel


class CoreInbound(BaseModel):
    tag: Optional[str] = None
    proto: str
    port: Optional[Union[int, str]] = None


class CoreStats(BaseModel):
    version: str
    started: bool
    logs_websocket: str
    inbounds: List[CoreInbound] = []
