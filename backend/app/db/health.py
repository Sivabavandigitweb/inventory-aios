from typing import Literal

from pydantic import BaseModel


class DatabaseHealthResponse(BaseModel):
    status: Literal["healthy", "not_configured", "unavailable"]
    database: Literal["postgresql"] = "postgresql"