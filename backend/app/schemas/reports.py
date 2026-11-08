from pydantic import BaseModel, Field, field_validator


class ReportCreate(BaseModel):
    report_type: str = Field(description="Suspected Adverse Event | Product Quality Complaint")
    product_name: str
    batch_lot_number: str
    date_received: str
    reporter_type: str
    description: str
    event_description: str | None = None
    event_onset_date: str | None = None

    @field_validator("report_type")
    @classmethod
    def validate_report_type(cls, v: str) -> str:
        allowed = {"Suspected Adverse Event", "Product Quality Complaint"}
        if v not in allowed:
            raise ValueError(f"report_type must be one of {sorted(allowed)}")
        return v


class StatusUpdateRequest(BaseModel):
    new_status: str
    # Optional on New→In Review; required when requesting Closed (pending HITL)
    reviewer_notes: str | None = None

    @field_validator("new_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"New", "In Review", "Closed"}
        if v not in allowed:
            raise ValueError(f"new_status must be one of {sorted(allowed)}")
        return v


class ApproveCloseRequest(BaseModel):
    confirm: bool = True
    comment: str | None = None


class RejectCloseRequest(BaseModel):
    confirm: bool = True
    note: str | None = None
