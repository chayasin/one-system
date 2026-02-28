from pydantic import BaseModel


class ServiceTypeResponse(BaseModel):
    code: str
    label: str
    channel: str | None

    model_config = {"from_attributes": True}


class ComplaintTypeResponse(BaseModel):
    code: str
    label: str

    model_config = {"from_attributes": True}


class ClosureReasonResponse(BaseModel):
    code: str
    label: str
    label_th: str
    requires_note: bool

    model_config = {"from_attributes": True}


class SlaConfigResponse(BaseModel):
    priority: str
    temp_fix_hours: int
    permanent_fix_days: int
    overdue_t1_days: int
    overdue_t2_days: int
    overdue_t3_days: int
    overdue_t4_days: int

    model_config = {"from_attributes": True}


class ProvinceItem(BaseModel):
    province: str
