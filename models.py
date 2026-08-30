from datetime import date
from typing import Literal, Optional, get_args

from pydantic import BaseModel, Field, model_validator

LeaveType = Literal["casual", "sick", "earned"]

LEAVE_TYPES = get_args(LeaveType)


def match_leave_type(value: str) -> Optional[str]:
    """Map a phrase onto a supported leave type, or None if it does not fit one.

    Users say "casual leave" rather than "casual", so an exact comparison alone
    would reject perfectly good answers.
    """
    value = value.strip().lower()

    if value in LEAVE_TYPES:
        return value

    matches = [name for name in LEAVE_TYPES if name in value]

    return matches[0] if len(matches) == 1 else None


class LeaveRequest(BaseModel):
    employee_name: str = Field(min_length=2, description="Name of the employee")
    employee_id: str = Field(min_length=2, description="Employee ID")
    leave_type: LeaveType = Field(description="Type of leave")
    start_date: date = Field(description="Leave start date")
    end_date: date = Field(description="Leave end date")

    reason: Optional[str] = Field(
        default=None,
        description="Reason for the leave. Return null if not provided."
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")

        return self


class PartialLeaveRequest(BaseModel):
    """A single turn's extraction: any field the user did not mention stays None."""

    employee_name: Optional[str] = None
    employee_id: Optional[str] = None
    leave_type: Optional[LeaveType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def drop_implausible(cls, data):
        """Turn unusable answers into None so the caller re-asks instead of failing.

        The model sometimes echoes a stray keystroke back as the answer to whatever
        was just asked. Discarding it here keeps that out of the state without
        raising, which would abort the turn.
        """
        if not isinstance(data, dict):
            return data

        cleaned = dict(data)

        leave_type = cleaned.get("leave_type")

        if isinstance(leave_type, str):
            cleaned["leave_type"] = match_leave_type(leave_type)

        for name in ("employee_name", "employee_id", "reason"):
            value = cleaned.get(name)

            if isinstance(value, str) and len(value.strip()) < 2:
                cleaned[name] = None

        return cleaned


FIELD_ORDER = list(PartialLeaveRequest.model_fields)

REQUIRED_FIELDS = [
    name
    for name, field in LeaveRequest.model_fields.items()
    if field.is_required()
]
