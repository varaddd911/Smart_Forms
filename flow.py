"""One user message in, one TurnResult out."""

from dataclasses import dataclass, field
from typing import Optional

from conversation import ConversationState
from llm_service import ExtractionError, extract_turn
from models import IntakeRecord
from prompts import FIELD_LABELS, OUT_OF_SCOPE_MESSAGE
from storage import save_intake_record

YES = {"yes", "y", "correct", "confirm", "confirmed", "looks good", "ok", "okay"}


@dataclass
class TurnResult:
    changed: list[str] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    next_field: Optional[str] = None
    error: Optional[str] = None
    unrecognised: Optional[str] = None
    out_of_scope: bool = False
    fallback_message: Optional[str] = None
    awaiting_confirmation: bool = False
    confirmation_message: Optional[str] = None
    saved_record: Optional[IntakeRecord] = None
    saved_path: Optional[str] = None


def is_user_confirmation(text: str) -> bool:
    return " ".join(text.lower().strip().replace(".", "").split()) in YES


def confirmation_message(record: IntakeRecord) -> str:
    return (
        "Please confirm the following regulatory intake:\n"
        f"Query type: {record.query_type.replace('_', ' ').title()}\n"
        f"Regulation reference: {record.regulation_ref}\n"
        f"Product area: {record.product_area.replace('_', ' ').title()}\n"
        f"Urgency: {record.urgency.title()}\n"
        f"Submitting team: {record.submitting_team}\n"
        "\nPlease confirm if these details are correct."
    )


def describe_changes(changed: list[str], values: dict) -> str:
    return ", ".join(f"{FIELD_LABELS[name].lower()} {values[name]}" for name in changed)


def process_turn(state: ConversationState, user_input: str, awaiting: Optional[str] = None) -> TurnResult:
    state.turns_taken += 1

    if state.awaiting_confirmation and is_user_confirmation(user_input):
        path = save_intake_record(state.pending_record, state.turns_taken)
        saved = state.pending_record
        result = TurnResult(values=saved.model_dump(), saved_record=saved, saved_path=str(path))
        state.reset()
        return result

    try:
        partial = extract_turn(
            user_input,
            known=state.get_state(),
            awaiting=awaiting,
            deadline_days=state.deadline_days,
        )
    except ExtractionError as exc:
        missing = state.missing_required_fields()
        return TurnResult(
            values=state.get_state(),
            next_field=awaiting or (missing[0] if missing else "query_type"),
            error=f"I could not read that ({exc})",
            awaiting_confirmation=state.awaiting_confirmation,
            confirmation_message=(
                confirmation_message(state.pending_record) if state.pending_record else None
            ),
        )

    if partial.out_of_scope:
        missing = state.missing_required_fields()
        return TurnResult(
            values=state.get_state(),
            next_field=missing[0] if missing else None,
            out_of_scope=True,
            fallback_message=OUT_OF_SCOPE_MESSAGE,
            awaiting_confirmation=state.awaiting_confirmation,
            confirmation_message=(
                confirmation_message(state.pending_record) if state.pending_record else None
            ),
        )

    changed = state.update_from(partial)
    missing = state.missing_required_fields()
    values = state.get_state()

    if missing:
        state.awaiting_confirmation = False
        state.pending_record = None
        stuck = awaiting if awaiting == missing[0] and awaiting not in changed else None
        return TurnResult(changed=changed, values=values, next_field=missing[0], unrecognised=stuck)

    record = state.to_intake_record()
    state.pending_record = record
    state.awaiting_confirmation = True
    return TurnResult(
        changed=changed,
        values=values,
        awaiting_confirmation=True,
        confirmation_message=confirmation_message(record),
    )
