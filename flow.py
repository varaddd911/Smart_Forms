"""Turn handling shared by the CLI and the Streamlit UI."""

from dataclasses import dataclass, field
from typing import Optional

from pydantic import ValidationError

from conversation import ConversationState
from llm_service import ExtractionError, extract_turn
from models import FIELD_ORDER, LeaveRequest
from prompts import FIELD_LABELS
from tools import submit_leave_request


@dataclass
class TurnResult:
    """What a single user message did to the conversation."""

    changed: list[str] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    next_field: Optional[str] = None
    submitted: Optional[LeaveRequest] = None
    error: Optional[str] = None
    unrecognised: Optional[str] = None


def process_turn(
    state: ConversationState,
    user_input: str,
    awaiting: Optional[str] = None,
) -> TurnResult:
    try:
        partial = extract_turn(
            user_input,
            known=state.get_state(),
            awaiting=awaiting,
        )
    except ExtractionError as exc:
        return TurnResult(
            values=state.get_state(),
            next_field=awaiting,
            error=f"I could not read that ({exc})",
        )

    changed = state.update_from(partial)

    # Snapshot before any clearing below, so callers can still report what landed.
    values = state.get_state()

    missing = state.missing_required_fields()

    if missing:
        # We asked for a field and the turn still did not produce it.
        stuck = awaiting if awaiting == missing[0] and awaiting not in changed else None

        return TurnResult(
            changed=changed,
            values=values,
            next_field=missing[0],
            unrecognised=stuck,
        )

    try:
        leave_request = state.to_leave_request()
    except ValidationError as exc:
        state.clear("start_date", "end_date")

        return TurnResult(
            changed=changed,
            values=values,
            next_field="start_date",
            error=exc.errors()[0]["msg"],
        )

    submit_leave_request(leave_request)
    state.clear(*FIELD_ORDER)

    return TurnResult(changed=changed, values=values, submitted=leave_request)


def describe_changes(changed: list[str], values: dict) -> str:
    return ", ".join(
        f"{FIELD_LABELS[field].lower()} {values[field]}"
        for field in changed
    )
