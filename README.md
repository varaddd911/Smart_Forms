# SmartIntake

Talk through a pharmaceutical regulatory query. The app extracts five fields,
asks for anything missing, shows a summary, and saves JSON only after you confirm.

No LangChain. OpenAI SDK extracts fields, Pydantic validates them, and ordinary
Python keeps conversation state.

## The five fields

| Field | Values |
| --- | --- |
| `query_type` | complaint, submission, variation, safety_signal, label_update, inspection, general_enquiry |
| `regulation_ref` | FDA_21CFR, EMA_CTR, ICH_E2A, ICH_Q10, CDSCO_NDC, GxP_GMP, GxP_GCP, other |
| `product_area` | oncology, cardiovascular, infectious_disease, cmc, clinical, labelling, general |
| `urgency` | routine, standard, urgent, critical |
| `submitting_team` | a team name (PV, CMC, Clinical, …), never a person |

Urgency comes from domain rules and the deadline, never from words like ASAP:

- SUSAR / ICH E2A expedited safety report → `critical` (even at 15 days)
- FDA Form 483 response → `urgent` (including a 15-business-day window)
- otherwise ≤48 hours → `critical`
- otherwise ≤3 days → `urgent`
- otherwise ≤2 weeks → `standard`
- otherwise weeks–months → `routine`
- no deadline and none of those domain triggers → ask for a date

MHRA (and other unlisted frameworks) → `other`.

## How it works

```
You type
  → prompt + OpenAI structured output
  → Pydantic (PartialIntakeRecord)
  → ConversationState keeps known fields
  → ask if something is missing
  → if complete, confirm
  → yes → output/intake_<timestamp>.json
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

```powershell
python app.py
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

## Files

| File | Role |
| --- | --- |
| `app.py` | CLI |
| `flow.py` | One turn: extract, merge, ask, confirm, save |
| `conversation.py` | Fields remembered across turns |
| `llm_service.py` | OpenAI call |
| `prompts.py` | System prompt and questions |
| `models.py` | Partial + final Pydantic models |
| `storage.py` | Confirmed JSON under `output/` |
| `audit.py` | Token log in `debug.json` |

Confirmed records and `debug.json` both use `log_safe: true` and never store the raw user message.
