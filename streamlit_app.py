from datetime import date

import streamlit as st

from conversation import ConversationState
from flow import describe_changes, process_turn
from llm_service import MODEL
from models import FIELD_ORDER, REQUIRED_FIELDS
from prompts import FIELD_LABELS, QUESTIONS

GREETING = (
    "Tell me about your leave request. You can describe it all at once, "
    "or answer one question at a time."
)

STYLES = """
<style>
    .field-row {
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 0.45rem 0.7rem;
        margin-bottom: 0.35rem;
        border-radius: 0.5rem;
        font-size: 0.875rem;
        line-height: 1.3;
    }
    .field-row.filled {
        background: rgba(33, 195, 84, 0.14);
        border: 1px solid rgba(33, 195, 84, 0.35);
    }
    .field-row.pending {
        border: 1px dashed rgba(140, 140, 140, 0.4);
    }
    .field-value {
        font-weight: 600;
        text-align: right;
    }
    .field-row.pending .field-value {
        font-weight: 400;
        font-style: italic;
        opacity: 0.6;
    }
</style>
"""


def init_session():
    if "state" in st.session_state:
        return

    st.session_state.state = ConversationState()
    st.session_state.awaiting = None
    st.session_state.submissions = []
    st.session_state.messages = [{"role": "assistant", "content": GREETING}]


def field_row(label, value, optional):
    if value is None:
        shown = "optional" if optional else "still needed"
        css = "pending"
    else:
        shown = value
        css = "filled"

    return (
        f"<div class='field-row {css}'>"
        f"<span>{label}</span>"
        f"<span class='field-value'>{shown}</span>"
        f"</div>"
    )


def render_sidebar():
    values = st.session_state.state.get_state()
    filled = [name for name in REQUIRED_FIELDS if values[name] is not None]

    with st.sidebar:
        st.subheader("Form progress")
        st.progress(
            len(filled) / len(REQUIRED_FIELDS),
            text=f"{len(filled)} of {len(REQUIRED_FIELDS)} required fields",
        )

        rows = "".join(
            field_row(
                FIELD_LABELS[name],
                values[name],
                optional=name not in REQUIRED_FIELDS,
            )
            for name in FIELD_ORDER
        )
        st.markdown(rows, unsafe_allow_html=True)

        if st.button("Start over", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        submissions = st.session_state.submissions

        if submissions:
            st.divider()
            st.caption(f"Submitted this session: {len(submissions)}")

        st.divider()
        st.caption(f"Model: {MODEL}")


def render_receipt(request):
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])

    with st.container(border=True):
        left, right = st.columns(2)

        left.markdown(f"**{request['employee_name']}**  \n{request['employee_id']}")
        right.markdown(
            f"**{request['leave_type']}**  \n{(end - start).days + 1} day(s)"
        )

        st.markdown(f"{start:%d %b %Y} to {end:%d %b %Y}")

        if request["reason"]:
            st.caption(request["reason"])


def render_history():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message.get("request"):
                render_receipt(message["request"])


def build_replies(result):
    if result.error:
        replies = [{"role": "assistant", "content": f"Sorry, {result.error}."}]
    elif result.submitted:
        replies = [{
            "role": "assistant",
            "content": "All set, I have submitted this request.",
            "request": result.submitted.model_dump(mode="json"),
        }]
    elif result.changed:
        summary = describe_changes(result.changed, result.values)
        replies = [{"role": "assistant", "content": f"Got {summary}."}]
    elif result.unrecognised:
        label = FIELD_LABELS[result.unrecognised].lower()
        replies = [{
            "role": "assistant",
            "content": f"That does not look like a {label}.",
        }]
    else:
        replies = [{
            "role": "assistant",
            "content": "I did not catch any new details there.",
        }]

    if result.next_field:
        replies.append({
            "role": "assistant",
            "content": QUESTIONS[result.next_field],
        })

    return replies


def handle_input(user_input):
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Reading your message"):
        result = process_turn(
            st.session_state.state,
            user_input,
            st.session_state.awaiting,
        )

    st.session_state.awaiting = result.next_field
    st.session_state.messages.extend(build_replies(result))

    if result.submitted:
        st.session_state.submissions.append(result.submitted.model_dump(mode="json"))


def main():
    st.set_page_config(page_title="Smart Forms", layout="centered")
    st.markdown(STYLES, unsafe_allow_html=True)

    init_session()

    st.title("Smart Forms")
    st.caption("Fill in a leave request by describing it in plain language.")

    render_sidebar()
    render_history()

    user_input = st.chat_input("Describe your leave request")

    if user_input and user_input.strip():
        handle_input(user_input.strip())
        st.rerun()


main()
