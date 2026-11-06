from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Health(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str
    service: str
    version: str
    environment: str
    db: str
    queue: str
