# Smart Forms

Fill in a structured form by talking to it. Instead of presenting an employee with
a leave-request form, this app collects the same information through conversation,
asks about whatever is still missing, and only submits once every required field
passes validation.

Built on the Gemini API with structured output, Pydantic for validation, and
Streamlit for the interface.

## What it does

Describe a leave request in plain language and the assistant extracts what it can:

```
You: I am Varad, employee ID E1024, casual leave
Assistant: Got employee name Varad, employee id E1024, leave type casual leave.
Assistant: Which date does the leave start?
You: September 10 to September 12
Assistant: All set, I have submitted this request.
```

Things it handles:

- **Partial information.** Give one field or all six, in any order.
- **Bare answers.** Replying just `E1024` works, because the model is told which
  question was asked.
- **Corrections.** Saying "make it sick leave instead" overwrites the earlier value.
- **Relative dates.** "September 10" resolves against today's date, never a past year.
- **Bad data.** An end date before the start date is rejected and re-asked.
- **Junk answers.** Leave type is constrained to `casual`, `sick` or `earned`, and a
  stray reply like `w` is discarded rather than stored, so the question is asked again.
  Natural phrasing such as "casual leave" still maps onto the right value.

## Project structure

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | Streamlit chat UI with a live form-progress sidebar |
| `app.py` | Terminal version of the same conversation |
| `flow.py` | Turn orchestration shared by both front ends |
| `conversation.py` | `ConversationState` — accumulates answers across turns |
| `llm_service.py` | Gemini client and per-turn extraction |
| `prompts.py` | System prompt, field labels, and the questions to ask |
| `models.py` | `LeaveRequest` (strict) and `PartialLeaveRequest` (per turn) |
| `tools.py` | Stand-in for the real submission backend |

## How it works

Each user message goes through the same five steps in `flow.process_turn`:

1. **Extract.** `llm_service.extract_turn` sends the message to Gemini with
   `response_schema=PartialLeaveRequest`, so the reply is JSON matching that model.
   The system prompt includes today's date, the fields already recorded, and the
   question just asked — that context is what makes bare replies and corrections work.
2. **Merge.** `ConversationState.update_from` copies over only the fields that came
   back non-`None`. This is what makes the conversation cumulative: a turn mentioning
   just the leave type must not erase the name captured three turns ago.
3. **Check.** `missing_required_fields()` reports what is still absent, and the front
   end asks about the first one.
4. **Validate.** Once nothing is missing, `to_leave_request()` builds a real
   `LeaveRequest`. Pydantic enforces the types and the end-after-start rule here.
5. **Submit.** `tools.submit_leave_request` is called and the state resets.

`LeaveRequest` is the single source of truth for what "required" means —
`REQUIRED_FIELDS` in `models.py` is derived from it by introspection, so the questions
asked can never drift from what validation actually demands.

## Setup

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

### API key

Create a key at [Google AI Studio](https://aistudio.google.com/apikey), then put it
in a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

`.env` is gitignored. `GEMINI_MODEL` is optional and defaults to
`gemini-3.5-flash-lite`.

## Running

Streamlit UI, served at http://localhost:8501:

```powershell
streamlit run streamlit_app.py
```

Or the terminal version:

```powershell
python app.py
```

Type `quit` to leave the CLI.

## Free tier quotas

The Gemini free tier allows roughly 20 requests per day **per model**, and every
conversation turn is one request. Two consequences worth knowing:

- Hitting `429 RESOURCE_EXHAUSTED` does not mean you are locked out. Because the
  quota is per model, switching `GEMINI_MODEL` to `gemini-3.5-flash` or
  `gemini-3.1-flash-lite` gives you a fresh bucket.
- Older model IDs such as `gemini-2.5-flash` and `gemini-2.0-flash` now return 404
  for new keys. Stick to the 3.x family.

Note also that keys beginning with `AQ.` are Vertex AI express-mode keys, which the
SDK routes to Agent Platform and which fail with `403 PERMISSION_DENIED` unless that
API is enabled on the Cloud project. `llm_service.py` passes `vertexai=False` to force
the Gemini Developer API for exactly this reason.

## Testing

The Streamlit app can be driven headlessly, without a browser:

```python
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("streamlit_app.py", default_timeout=90)
at.run()
at.chat_input[0].set_value("I am Varad, employee ID E1024, casual leave").run()

print(at.session_state.state.get_state())
```

Each simulated turn makes a real API call and counts against your quota. The state
logic in `conversation.py` can be tested without any calls by constructing
`PartialLeaveRequest` objects directly and passing them to `update_from`.

## Possible next steps

- Preserve employee name and ID across submissions instead of clearing every field.
- Let the user unset an optional field; `update_from` currently ignores `None`, so
  "actually there's no reason" cannot clear `reason`.
- Persist submissions somewhere real rather than printing them.
- Support more form types by generalising `LeaveRequest` into one schema among several.
