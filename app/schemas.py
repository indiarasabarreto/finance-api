from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models import GroupType, PaymentStatus

class EventConsumptionBase(BaseModel):
    person_name: str
    group: GroupType
    raw_items: str
    total_amount: float
    status: PaymentStatus

class EventConsumptionCreate(EventConsumptionBase):
    pass

class EventConsumptionResponse(EventConsumptionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime