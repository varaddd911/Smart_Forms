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

Urgency comes from the deadline, not from words like ASAP:

- due today / overdue → critical
- 1–7 days → urgent
- 8–30 days → standard
- more than 30 days → routine
- no deadline → ask for one

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
