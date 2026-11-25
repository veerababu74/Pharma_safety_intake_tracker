import re

from pydantic import BaseModel, Field, field_validator, model_validator

LOT_RE = re.compile(r"^LOT-\d{5}$")


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

    @field_validator("batch_lot_number")
    @classmethod
    def validate_lot(cls, v: str) -> str:
        lot = (v or "").strip().upper()
        if not LOT_RE.match(lot):
            raise ValueError("batch_lot_number must match LOT-##### (exactly 5 digits)")
        return lot

    @model_validator(mode="after")
    def validate_ae_fields(self) -> "ReportCreate":
        if self.report_type == "Suspected Adverse Event":
            if not (self.event_description or "").strip():
                raise ValueError("event_description is required for Suspected Adverse Event")
            if not (self.event_onset_date or "").strip():
                raise ValueError("event_onset_date is required for Suspected Adverse Event")
        return self


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
