# Radiologist-Scheduling-Agent

A web application that converts free-form natural-language notes from radiologists into a balanced on-call rota.
Two core components underpin the system:
	1.	Large-language-model (LLM) agents (OpenAI GPT models) — transform narrative notes into structured, machine-readable constraints;
	2.	CP-SAT optimisation model (Google OR-Tools) — produces a schedule that satisfies all hard rules and minimises specified soft penalties.

⸻

## 1 Repository structure

```text
Radiologist-Scheduling-Agent/
├─ home.py                          ← Streamlit user interface (entry point)
│
├─ utils/
│   ├─ parse/
│   │   ├─ __init__.py
│   │   ├─ parse_AI.py              ← LLM-driven parsers
│   │   ├─ parse_non_AI.py          ← CSV helpers
│   │   └─ parse_requests.py        ← Orchestrates agents + scheduling logic
│   │
│   ├─ schedule/
│   │   ├─ __init__.py
│   │   ├─ alterations.py           ← Post-processing mutators
│   │   ├─ objective.py             ← Objective-function builder
│   │   ├─ scheduler.py             ← CP-SAT model generator
│   │   └─ variables.py             ← Decision-variable helpers
│   │
│   └─ __init__.py
│
├─ tests/
│   ├─ test_parse_requests.py
│   ├─ schedule-test.py
│   └─ test_alterations.py
│
├─ data/
│   ├─ radiologist_profiles.csv
│   └─ shift_data_single_month.csv
│
└─ README.md


⸻

## 2 System overview

Stage	Principal modules	Summary
Data ingestion	home.py	User uploads two CSV files: (i) shift template and (ii) radiologist profiles.
Natural-language parsing	utils/parse/parse_AI.py, parse_requests.py	OpenAI agents derive availability matrices, explicit shift requests, monthly-cap amendments, and any direct “edit” operations (add / remove / swap).
Initial optimisation	utils/schedule/scheduler.py	Builds a CP-SAT model with one Boolean variable per (employee, shift). Hard constraints: availability, single-assignment per slot, monthly caps. Soft objectives defined in objective.py.
Post-edit processing	utils/schedule/alterations.py	Direct edits are applied immediately; otherwise a full re-optimisation is invoked.
Presentation layer	home.py	Calendar and legend are rendered; uncovered shifts can be exported for “moonlighting” coverage.

Error-handling safeguards
	•	Each LLM extractor retries up to three attempts before raising a ValueError.
	•	Malformed keys in requested_shift_map are logged and discarded.
	•	Unknown radiologists referenced in a note are added automatically with a default monthly cap (five shifts) and full availability.

⸻

## 3 Installation and execution

### 3.1 Environment setup

git clone https://github.com/<your-user>/Radiologist-Scheduling-Agent.git
cd Radiologist-Scheduling-Agent

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt      # OR-Tools, Streamlit, pandas, openai, …
export OPENAI_API_KEY=<your-key>

### 3.2 Running the automated tests

python3 -m tests.test_parse_requests
python3 -m tests.schedule-test
python3 -m tests.test_alterations

### 3.3 Starting the application

streamlit run ./home.py

The application should open automatically; if not, open the URL shown in the terminal.

For an instant trial, select data/radiologist_profiles.csv and data/shift_data_single_month.csv when uploading files.

⸻

## 4 Operating the application
### 1.	Step 1 — Upload input files
Scheduling CSV (columns Date, Shift with values L1/L2/L3) and Radiologist profile CSV (columns Radiologist_ID, Notes).
Click Create Schedule to generate the initial calendar.
### 2.	Moonlighting export (optional)
If any shifts remain uncovered, a Moonlighting Shifts Export button appears; click to download a CSV of open slots.
### 3.	Step 2 — Submit additional notes
Enter the requestor’s name, type a free-text note, and press Submit.
Examples:
	•	“I can only cover July 15 L2 and L3.”
	•	“Please swap my August 3 L1 shift with Alice.”
	•	“My maximum for this month is three shifts.”
The calendar, legend, and underlying data structures refresh automatically.

⸻

## 5 Customisation guidelines
	•	Objective weights — adjust utils/schedule/objective.py.
	•	Additional hard constraints — add model.Add(...) statements in scheduler.py.
	•	Model selection — each Agent sets its OpenAI model via the model= argument (default gpt-4o).
	•	Logging — console output highlights discarded agent data and auto-generated defaults.

⸻

## 6 Dependencies

The project targets Python 3.9 + and relies on the following core packages (see requirements.txt for exact versions):

Package	Purpose
openai	Access to GPT models for parsing tasks
google-ortools	CP-SAT optimiser
streamlit	Web UI framework
pandas	CSV processing
python-dotenv (optional)	Local .env management for OPENAI_API_KEY
pytest / unittest	Test execution (used by the scripts in tests/)

Install them collectively via pip install -r requirements.txt as shown earlier.
