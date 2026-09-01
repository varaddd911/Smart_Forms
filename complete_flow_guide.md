# Complete Flow Guide

This file walks through Smart Forms from startup to submit. It names the real
files, classes, and functions, then dry-runs a leave request turn by turn.

There are two front ends — Streamlit (`streamlit_app.py`) and the CLI (`app.py`).
Both call the same function for every user message:

```python
result = process_turn(state, user_input, awaiting)
```

That function lives in `flow.py`. Everything else hangs off it.

---

## 1. What each file does

| File | Role |
| --- | --- |
| `streamlit_app.py` | Chat UI, sidebar progress, chat history |
| `app.py` | Terminal version of the same conversation |
| `flow.py` | `process_turn()` — one message in, one `TurnResult` out |
| `conversation.py` | `ConversationState` — memory of answers so far |
| `llm_service.py` | OpenAI client + `extract_turn()` |
| `prompts.py` | System prompt, field labels, follow-up questions |
| `models.py` | `PartialLeaveRequest` (per turn) and `LeaveRequest` (final form) |
| `tools.py` | Fake backend: prints the submitted request |

Mental model:

```
You talk
  → OpenAI extracts fields into PartialLeaveRequest
  → ConversationState merges them
  → if something required is still missing, ask the next question
  → if complete, Pydantic validates a LeaveRequest
  → tools.py "submits" it and state is cleared
```

---

## 2. Startup (before anyone types)

### Streamlit — `streamlit_app.main()`

1. `init_session()` creates:
   - `st.session_state.state` → empty `ConversationState()`
   - `st.session_state.awaiting` → `None` (no question asked yet)
   - `st.session_state.messages` → greeting
   - `st.session_state.submissions` → `[]`
2. `get_client()` in `llm_service.py` reads `OPENAI_API_KEY` from `.env`
   (or Streamlit secrets if deployed). Missing key → error and stop.
3. Sidebar shows **0 of 5 required fields**. Chat shows the greeting.

### CLI — `app.main()`

Same idea without Streamlit: `get_client()`, then `ConversationState()` and
`awaiting = None`, then a `while True` loop on `input("You: ")`.

### Empty state after startup

```python
{
  "employee_name": None,
  "employee_id": None,
  "leave_type": None,
  "start_date": None,
  "end_date": None,
  "reason": None,
}
```

Required fields (from `LeaveRequest` in `models.py`): name, ID, leave type,
start date, end date. `reason` is optional.

---

## 3. One turn — the five steps in `process_turn`

Every user message, in both UIs, goes through this pipeline in `flow.py`.

```
handle_input() / CLI loop
        │
        ▼
process_turn(state, user_input, awaiting)
        │
        ├─ 1. extract_turn()          llm_service.py  → PartialLeaveRequest
        ├─ 2. state.update_from()     conversation.py → list of changed fields
        ├─ 3. missing_required_fields()               → next question, or continue
        ├─ 4. state.to_leave_request() models.py      → LeaveRequest (or ValidationError)
        └─ 5. submit_leave_request()  tools.py        → print + clear state
```

### Step 1 — Extract (`llm_service.extract_turn`)

OpenAI is called with:

- **System prompt** from `get_smart_form_prompt(known, awaiting)` in `prompts.py`
  (today's date, already-recorded fields, the question just asked).
- **User message** as the latest turn.
- **`response_format=PartialLeaveRequest`** so the reply is structured JSON,
  not free text.

`None` in the partial means "the user did not mention this field **this turn**".
It does **not** mean "delete this field".

`PartialLeaveRequest.drop_implausible()` then cleans junk before merge:
`"casual leave"` → `"casual"`, a stray `"w"` → `None`.

If the API fails or the model refuses, `ExtractionError` is raised and
`process_turn` returns an error `TurnResult`. State is unchanged.

### Step 2 — Merge (`ConversationState.update_from`)

Only non-`None` values that actually differ from what is already stored are
written. That is why the conversation is cumulative: a turn that only mentions
leave type cannot wipe the name captured earlier.

### Step 3 — Check missing fields

`missing_required_fields()` walks `REQUIRED_FIELDS` in order and returns the
ones that are still `None`.

If anything is missing:

- `next_field` = the first missing field (the UI asks `QUESTIONS[next_field]`)
- `unrecognised` is set if we had just asked for that field and it still did
  not land (e.g. the user typed `"w"` for leave type)

### Step 4 — Validate (`state.to_leave_request`)

When nothing required is missing, `LeaveRequest.model_validate(...)` runs.
Pydantic checks types, min lengths, leave type ∈ `{casual, sick, earned}`, and
`end_date >= start_date`.

If dates are backwards, `process_turn` clears only `start_date` and `end_date`
and asks for the start date again. Name, ID, and leave type stay.

### Step 5 — Submit (`tools.submit_leave_request`)

On success the request is printed (stand-in for a real HR backend), then
`state.clear(*FIELD_ORDER)` resets every field so the next request can start
fresh. The UI gets `TurnResult.submitted`.

---

## 4. How the UI reads `TurnResult`

Both front ends look at the same fields:

| Field | User sees |
| --- | --- |
| `changed` | "Got employee name Varad, leave type casual." |
| `next_field` | Follow-up question from `QUESTIONS` |
| `unrecognised` | "That does not look like a [field]." then re-ask |
| `error` | "Sorry, …" |
| `submitted` | "All set, I have submitted this request." (+ receipt in Streamlit) |

Streamlit does this in `build_replies()`. The CLI does it with `print()`.

---

## 5. Dry run — Varad takes leave

Story: Varad fills the form over three messages in Streamlit, on 1 Sep 2026.

---

### Turn 1 — `"I am Varad, employee ID E1024, casual leave"`

**Call chain**

```
User types in the chat box
  → streamlit_app.main() sees user_input
  → handle_input("I am Varad, employee ID E1024, casual leave")
      → process_turn(state, that string, awaiting=None)
          → extract_turn(...)
```

`awaiting` is `None`, so the prompt does not hint at a specific field. OpenAI
returns something like:

```json
{
  "employee_name": "Varad",
  "employee_id": "E1024",
  "leave_type": "casual",
  "start_date": null,
  "end_date": null,
  "reason": null
}
```

That JSON becomes a `PartialLeaveRequest`. `drop_implausible()` leaves it as-is
(`"casual"` is already a valid leave type).

Then:

```python
changed = state.update_from(partial)
# ["employee_name", "employee_id", "leave_type"]

missing = state.missing_required_fields()
# ["start_date", "end_date"]
```

Still missing fields, so no validate/submit. Returns:

```python
TurnResult(
    changed=["employee_name", "employee_id", "leave_type"],
    next_field="start_date",
)
```

**UI** (`build_replies`):

1. "Got employee name Varad, employee id E1024, leave type casual."
2. "Which date does the leave start?"   ← `QUESTIONS["start_date"]`

Sidebar: **3 of 5** required fields. `awaiting` is now `"start_date"`.

---

### Turn 2 — `"September 10"`

Now `awaiting = "start_date"`. The system prompt includes:

```
Already recorded:
- Employee name: Varad
- Employee ID: E1024
- Leave type: casual

The question just asked was: Start date
```

That is why a bare `"September 10"` maps to `start_date`, not to name or ID.
The model also fills in the year from today's date (rule 4 in the prompt),
so the date becomes `2026-09-10`.

```json
{
  "employee_name": null,
  "employee_id": null,
  "leave_type": null,
  "start_date": "2026-09-10",
  "end_date": null,
  "reason": null
}
```

`update_from` writes only `start_date`. Earlier values stay.

```python
changed = ["start_date"]
missing = ["end_date"]
next_field = "end_date"
```

**UI:**

1. "Got start date 2026-09-10."
2. "Which date does the leave end?"

---

### Turn 3 — `"September 12"`

Same pattern. After merge:

```python
{
  "employee_name": "Varad",
  "employee_id": "E1024",
  "leave_type": "casual",
  "start_date": date(2026, 9, 10),
  "end_date": date(2026, 9, 12),
  "reason": None,
}

missing = []   # every required field is filled
```

`process_turn` continues:

```python
leave_request = state.to_leave_request()
# LeaveRequest.validate_dates(): 12 Sep >= 10 Sep → OK

submit_leave_request(leave_request)   # tools.py prints the request
state.clear(*FIELD_ORDER)             # all fields back to None
```

Returns `TurnResult(submitted=leave_request, next_field=None)`.

**UI:**

- "All set, I have submitted this request."
- Receipt card via `render_receipt()`
- Request appended to `st.session_state.submissions`

State is empty again. The next message starts a new request.

---

## 6. Other scenarios (same pipeline, different branch)

### Everything in one message

User: `"Varad, E1024, sick leave, Sept 10 to Sept 12, family function"`

One trip through `process_turn`: extract fills all five required fields plus
reason → `missing = []` → validate → submit → clear. No follow-up questions.

### Junk answer while a question is pending

Context: `awaiting = "leave_type"`. User types `"w"`.

OpenAI may echo `"leave_type": "w"`. Then
`match_leave_type("w")` returns `None`, so the partial has `leave_type=None`.

```python
changed = []
missing[0] = "leave_type"
unrecognised = "leave_type"   # we asked for it, it still did not land
```

UI: "That does not look like a leave type." then re-asks the leave-type
question. State is not corrupted.

### End date before start date

All fields fill, `missing = []`, then `LeaveRequest.validate_dates()` raises
`ValidationError`.

```python
state.clear("start_date", "end_date")
TurnResult(error="End date cannot be before start date.", next_field="start_date")
```

Name, ID, and leave type stay. Only dates are wiped.

### Correction

State has `leave_type = "casual"`. User says `"actually make it sick leave"`.

The partial comes back with `leave_type="sick"`. `update_from` sees it differs
from the stored value and overwrites. There is no separate "edit mode".

### API failure

`extract_turn` raises `ExtractionError`. `process_turn` returns
`TurnResult(error="I could not read that (...)", next_field=awaiting)`.
State is unchanged; the user can retry.

---

## 7. Full call stack for one turn

```
streamlit_app.handle_input(user_input)
  └── flow.process_turn(state, user_input, awaiting)
        ├── llm_service.extract_turn()
        │     ├── get_client()                         # OpenAI, cached
        │     ├── prompts.get_smart_form_prompt()
        │     └── chat.completions.parse(
        │           response_format=PartialLeaveRequest
        │         )
        │           └── models.drop_implausible()
        │                 └── match_leave_type()
        ├── conversation.ConversationState.update_from()
        ├── conversation.ConversationState.missing_required_fields()
        ├── [if complete] ConversationState.to_leave_request()
        │     └── LeaveRequest.model_validate()
        │           └── validate_dates()
        ├── [if valid] tools.submit_leave_request()
        └── return TurnResult
              └── streamlit_app.build_replies()
                    ├── flow.describe_changes()
                    └── prompts.QUESTIONS[next_field]
```

The CLI skips `handle_input` / `build_replies` and prints `TurnResult` itself.
The core from `process_turn` down is identical.

---

## 8. Objects and how long they live

| Object | Created | Lives in | Gone when |
| --- | --- | --- | --- |
| `ConversationState` | `init_session()` / CLI `main()` | session / local variable | "Start over", new session, or process exit |
| `PartialLeaveRequest` | each OpenAI response | one turn | discarded after merge |
| `LeaveRequest` | when the form is complete and valid | `TurnResult.submitted` | copied into Streamlit `submissions` |
| `TurnResult` | each `process_turn()` | returned to the UI | discarded after the UI reads it |
| `awaiting` | updated every turn | `st.session_state.awaiting` or CLI local | tracks the last question asked |

---

## 9. Glossary

| Term | Meaning here |
| --- | --- |
| **Turn** | One user message → one extract → one merge → one reply |
| **Structured output** | Force the model to reply as JSON matching a Pydantic model |
| **`PartialLeaveRequest`** | What this turn mentioned; unmentioned fields stay `None` |
| **`LeaveRequest`** | The finished, validated form |
| **`ConversationState`** | Running total of answers across turns |
| **`awaiting`** | Hint in the prompt: "the user is probably answering this field" |
| **`None` in a partial** | "Not mentioned this turn" — not "clear this field" |
| **`REQUIRED_FIELDS`** | Derived from `LeaveRequest` by introspection, so questions and validation cannot drift apart |
