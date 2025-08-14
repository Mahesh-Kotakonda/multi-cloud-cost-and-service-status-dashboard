from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class MetricIn(BaseModel):
    resource_name: str = Field(..., example="demo-resource")
    cpu_usage: float = Field(..., ge=0, le=100, example=34.5)
    memory_usage: float = Field(..., ge=0, le=100, example=62.1)
    status: str = Field(..., example="healthy")

class MetricOut(BaseModel):
    id: int
    resource_name: str
    cpu_usage: float
    memory_usage: float
    status: str
    created_at: datetime
