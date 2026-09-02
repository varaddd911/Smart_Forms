# Complete flow

SmartIntake turns a conversation into a validated regulatory intake record.

A user does not fill a form. They describe a query in plain language. The
application extracts five fields, asks only for what is still missing, shows a
summary, and writes JSON **only after the user confirms**.

This file explains that path end to end, why each step exists, and what happens
on a real conversation.

---

## Why this design

The job is intake, not a chatbot and not a one-shot extractor.

| Need | How this project meets it |
| --- | --- |
| The user may give one field or all five | Multi-turn conversation, not a single API call |
| The model can guess or invent | Pydantic checks values; Python refuses to save incomplete records |
| Tone words like "ASAP" are not a deadline | Urgency is computed from domain rules and `deadline_days`, never from emotion |
| A wrong save is worse than a slow save | Confirmation happens before `output/` is written |
| Regulatory text is sensitive | Stored JSON and `debug.json` never contain the raw user message |
| The code must be easy to explain | OpenAI SDK + Pydantic + ordinary Python. No LangChain |

LangChain is intentionally not used. The OpenAI SDK already returns structured
JSON. Conversation memory is five variables on `ConversationState`. Orchestration
is one function: `process_turn` in `flow.py`. Adding a chain framework would hide
the path this document is meant to make obvious.

---

## The five fields

The final record has exactly these business fields:

1. `query_type` — complaint, submission, variation, safety_signal, label_update, inspection, general_enquiry
2. `regulation_ref` — FDA_21CFR, EMA_CTR, ICH_E2A, ICH_Q10, CDSCO_NDC, GxP_GMP, GxP_GCP, other
3. `product_area` — oncology, cardiovascular, infectious_disease, cmc, clinical, labelling, general
4. `urgency` — routine, standard, urgent, critical
5. `submitting_team` — a team or function (PV, CMC, Clinical, Labelling, Submissions, …), never a person

`deadline_days`, `is_expedited_safety`, `is_form_483`, and `out_of_scope` exist
only during the conversation. They are not written to the saved JSON.

Urgency mapping (Python, not the LLM):

- SUSAR / ICH E2A expedited safety report → `critical`
- FDA Form 483 → `urgent`
- otherwise ≤48 hours (including tomorrow) → `critical`
- otherwise ≤3 days → `urgent`
- otherwise ≤14 days → `standard`
- otherwise weeks–months → `routine`
- no usable deadline and none of those domain triggers → field stays empty and the app asks for a date

---

## Architecture

```
User
  ↓
CLI                         app.py
  ↓
Prompt                      prompts.py
  ↓
OpenAI SDK                  llm_service.py
  ↓
Pydantic                    models.py  (PartialIntakeRecord)
  ↓
Conversation state          conversation.py
  ↓
Orchestration               flow.py  (process_turn)
  ↓
Confirmation
  ↓
Storage                     storage.py  → output/intake_<timestamp>.json
```

`debug.json` is written beside these steps whenever OpenAI is called. It stores
token counts only.

---

## What each file is for

| File | Role |
| --- | --- |
| `app.py` | Reads `You:` input, prints the assistant reply, loops until `quit` |
| `prompts.py` | System prompt, field labels, clarification questions |
| `llm_service.py` | OpenAI structured-output call, up to two retries |
| `models.py` | `PartialIntakeRecord` (one turn) and `IntakeRecord` (final five fields) |
| `conversation.py` | Running total of known fields across turns |
| `flow.py` | Decides: ask, confirm, save, or fallback |
| `storage.py` | Writes the confirmed JSON |
| `audit.py` | Appends one JSON line to `debug.json` |

The CLI never contains business rules. Every user message goes through
`process_turn`. That is why the flow stays in one place.

---

## Step by step

### 1. User input — `app.py`

`main()` checks that `OPENAI_API_KEY` exists, creates an empty
`ConversationState`, and waits for a line of text.

Empty input is ignored. `quit` / `exit` ends the loop. Anything else is one
**turn**.

### 2. Prompt — `prompts.py`

`get_smart_form_prompt` builds a system prompt that:

- names the five fields and their allowed values
- says extract only what this message actually contains
- says do not invent a `regulation_ref` (MHRA → `other`)
- says do not treat ASAP as a deadline
- says a person is not a `submitting_team`
- includes already-recorded values so the model does not wipe them with null
- includes two few-shot examples and three negatives (tone, person-as-team, citation beats agency name)

If the app just asked a question, the prompt also says which field that question
was about. That is why a bare answer such as `"inspection"` can be mapped.

**Why a dedicated prompt file:** the extraction rules live in one place, not
scattered through `flow.py`.

### 3. OpenAI SDK — `llm_service.py`

`extract_turn` calls `chat.completions.parse` with
`response_format=PartialIntakeRecord` and `max_tokens=300`. The model must
return JSON that matches the Pydantic model, not free prose.

If the call fails, it retries at most twice (three attempts total), then raises
`ExtractionError`. The app does not crash and does not invent values.

After each call, `audit.log_llm_usage` appends a line to `debug.json`:

```json
{
  "event": "llm_call_completed",
  "input_tokens": 120,
  "output_tokens": 85,
  "elapsed_ms": 410,
  "timestamp": "...",
  "log_safe": true
}
```

User text, prompts, and extracted field values are not logged.

### 4. Pydantic — `models.py`

Two models on purpose:

- **`PartialIntakeRecord`** — used every turn. Any field may be `None`. Invalid
  enum values become `None` instead of raising, so the conversation can ask
  again. `urgency` from the model is discarded. Python sets urgency from SUSAR /
  Form 483 flags and the deadline table. `refine_partial` then prefers an
  explicit ICH E2A / SUSAR citation over an agency name such as EMA.
- **`IntakeRecord`** — used only when all five fields are filled. Strict types.
  Empty team and person names (`John`) are rejected.

**Why two models:** a partial turn must be allowed to succeed. The final record
must not.

### 5. Conversation state — `conversation.py`

`ConversationState` holds the five fields plus `deadline_days`, the SUSAR and
Form 483 flags, `turns_taken`, and a pending record waiting for confirmation.

`update_from` copies only non-`None` values. `None` means "this turn did not
mention the field", not "clear it". That is what makes the conversation
cumulative.

`missing_required_fields()` returns the five fields that are still `None`, in
order.

### 6. Orchestration — `flow.py`

`process_turn(state, user_input, awaiting)` does the following, in order:

1. Count the turn.
2. If a confirmation is pending and the user said yes / confirm / looks good →
   save and reset. Stop.
3. If a confirmation is pending and the user said a bare `no` / `nope` /
   `incorrect` / `wrong` → do **not** call OpenAI. Ask which of the five fields
   to change. Stay in confirmation.
4. Otherwise call the LLM and get a `PartialIntakeRecord`. A longer correction
   such as `no, regulation is ICH E2A` updates only the mentioned field.
5. If that fails → return an error and re-ask. Do not change state.
6. If `out_of_scope` → explain that SmartIntake is for regulatory intake. Do
   not force a `query_type`.
7. Merge into `ConversationState`.
8. If something is still missing → set `next_field` so the CLI asks
   `QUESTIONS[next_field]`.
9. If all five fields are valid → store `pending_record` and return a
   confirmation message. **Do not save.**

The LLM extracts. `flow.py` decides what happens next.

Clarification questions (from `prompts.py`):

- query type: which of the seven types is this?
- regulation: which framework applies, if known?
- product area: which of the seven areas?
- urgency: what is the **deadline**, not "how urgent do you feel"?
- team: PV, CMC, Clinical, Labelling, Submissions, or another team?

### 7. Confirmation

When the five fields are complete, the user sees:

```
Please confirm the following regulatory intake:
Query type: Inspection
Regulation reference: FDA_21CFR
Product area: Oncology
Urgency: Urgent
Submitting team: CMC

Please confirm if these details are correct.
```

Nothing is in `output/` yet.

- `yes` / `correct` / `confirm` / `looks good` → save
- a bare `no` → list the five fields; stay in confirmation; do not call OpenAI
- a correction such as `PV will handle it instead` → merge that field, confirm again

**Why confirm before save:** intake records are audit artefacts. A silent wrong
save is worse than one extra turn.

### 8. Storage — `storage.py`

`save_intake_record` writes `output/intake_<timestamp>.json`:

```json
{
  "query_type": "inspection",
  "regulation_ref": "FDA_21CFR",
  "product_area": "oncology",
  "urgency": "urgent",
  "submitting_team": "CMC",
  "timestamp": "2026-09-02T15:00:00+00:00",
  "turns_taken": 4,
  "log_safe": true
}
```

Only those keys. No original message, no chat history, no `deadline_days`.

Then `ConversationState.reset()` so the next query starts empty.

---

## Dry run

Story: FDA inspection on an oncology product, filled over several turns.

### Startup

```
query_type        None
regulation_ref    None
product_area      None
urgency           None
submitting_team   None
turns_taken       0
```

### Turn 1

**You:** We have an FDA issue with our oncology product.

The model can take FDA and oncology. It should **not** invent `query_type`
(inspection vs complaint vs submission is still unclear). No deadline, so no
urgency.

After merge:

```
query_type        None
regulation_ref    FDA_21CFR
product_area      oncology
urgency           None
submitting_team   None
```

Missing, in order: query_type, urgency, submitting_team.

**Assistant:** Is this a complaint, submission, variation, safety signal, label update, inspection, or general enquiry?

`output/` is still empty.

### Turn 2

**You:** It is an inspection matter.

Extraction: `query_type=inspection`. Other fields null. Null does not erase
`FDA_21CFR` or `oncology`.

```
query_type        inspection
regulation_ref    FDA_21CFR
product_area      oncology
urgency           None
submitting_team   None
```

**Assistant:** What is the actual regulatory deadline or required response date?

(Urgency is asked as a deadline on purpose.)

### Turn 3

**You:** CMC will handle it and the response is due tomorrow.

Extraction: `submitting_team=CMC`, `deadline_days=1`, `urgency` left null by the
model. Pydantic sets `urgency=critical` because tomorrow is within 48 hours.

```
query_type        inspection
regulation_ref    FDA_21CFR
product_area      oncology
urgency           critical
submitting_team   CMC
```

Nothing missing. `pending_record` is set. Confirmation is shown. **Not saved.**

### Turn 4 — confirmation

**Assistant:** Please confirm the following regulatory intake: …

### Turn 5

**You:** Yes.

`save_intake_record` writes the JSON above (`turns_taken` is 4: three extracting
messages plus `Yes`). State is cleared. The next message is a new intake.

---

## Other paths (same `process_turn`)

**Happy path.** One message already contains all five fields (with a real
deadline). The app skips the questions and goes straight to confirmation.

**Correction.** After the summary, the user says `PV will handle it instead`.
The team is updated, the other four fields stay, confirmation is shown again,
save still waits for `yes`. A regulation-only correction such as
`no, regulation is ICH E2A` does not cascade into the other fields.

**Bare no.** After the summary, `no` does not mark the query out of scope.
The app asks which field to change. Urgency can only be changed by giving a
deadline, not by typing `critical`.

**Out of scope.** "What should I cook for dinner?" → `out_of_scope=true`.
The assistant explains SmartIntake is for regulatory intake. Existing fields
are not overwritten with a fake `query_type`.

**Extraction failure.** OpenAI errors or empty parses are retried twice. If they
still fail, the user is asked to rephrase. State is unchanged.

**Invalid values.** A junk enum becomes `None` on the partial model. A person
name is not accepted as `submitting_team`. The app asks again instead of
crashing.

---

## Call stack for one extracting turn

```
app.main
  └── flow.process_turn
        ├── llm_service.extract_turn
        │     ├── prompts.get_smart_form_prompt
        │     ├── OpenAI chat.completions.parse(PartialIntakeRecord)
        │     └── audit.log_llm_usage          # tokens only
        ├── conversation.ConversationState.update_from
        ├── conversation.ConversationState.missing_required_fields
        └── if complete: pending confirmation, no storage yet
```

On a confirming `yes`:

```
flow.process_turn
  └── storage.save_intake_record → output/intake_<timestamp>.json
```
