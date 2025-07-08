# Radiologist-Scheduling-Agent
A web application that converts free-form natural-language notes from radiologists into a balanced on-call rotation. Two core components underpin the system:

1. **Large-language-model (LLM) agents** (OpenAI GPT models) — transform narrative notes into structured, machine-readable constraints.  
2. **CP-SAT optimisation model** (Google OR-Tools) — produces a schedule that satisfies all hard rules and minimises specified soft penalties.

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
```


⸻

## 2 System overview

| **Stage** | **Principal module(s)** | **Summary** |
|-----------|-------------------------|-------------|
| **Data ingestion** | `home.py` | User uploads two CSV files: the shift template and the radiologist-profile sheet. |
| **Natural-language parsing** | `utils/parse/parse_AI.py`, `parse_requests.py` | OpenAI agents convert free-text notes into structured data: availability matrices, explicit shift requests, monthly-cap changes, and direct “edit” actions (add / remove / swap). |
| **Initial optimisation** | `utils/schedule/scheduler.py` | Builds a CP-SAT model with one Boolean variable per (employee, shift). Enforces hard constraints (availability, single-assignment per slot, monthly caps) and minimises soft penalties defined in `objective.py`. |
| **Post-edit processing** | `utils/schedule/alterations.py` | Applies direct edits immediately; if no edits are specified, triggers a complete re-optimisation. |
| **Presentation layer** | `home.py` | Renders the calendar and colour legend; uncovered shifts can be exported for “moonlighting” coverage. |

<details>
<summary><strong>Error-handling safeguards</strong></summary>

- **Three-retry policy** – every LLM extractor attempts the prompt up to **three times** before propagating a `ValueError`.
- **Auto-provisioning of unknown radiologists** – when a note mentions a radiologist not yet in the data set, the system automatically  
  inserts that name with:
  - a default monthly cap of **five shifts**, and  
  - full availability (all shifts set to `1`),  
  unless the note explicitly states otherwise.
</details>

⸻

## 3 Installation and execution

### 3.1 Environment setup

<pre lang="markdown">

<code>
git clone https://github.com/&lt;your-user&gt;/Radiologist-Scheduling-Agent.git
cd Radiologist-Scheduling-Agent

python3 -m venv .venv
source .venv/bin/activate

# Install necessary packages:
pip install openai google-ortools streamlit pandas

# Set your OpenAI API key
export OPENAI_API_KEY=&lt;your-key&gt;
</code>

</pre>


### 3.2 Running the automated tests
<pre lang="markdown">

<code>
python3 -m tests.test_parse_requests
python3 -m tests.schedule-test
python3 -m tests.test_alterations
</code>

</pre>

### 3.3 Starting the application
<pre lang="markdown">

<code>
streamlit run ./home.py
</code>

</pre>

The application should open automatically; if not, open the URL shown in the terminal.

Select `data/radiologist_profiles.csv` and `data/shift_data_single_month.csv` when uploading files for a functioning example.

⸻

## 4 Operating the application
### 1.	Step 1 — Upload input files
Scheduling CSV (columns: Date, Shift with values L1/L2/L3) and Radiologist profile CSV (columns: Radiologist_ID, Notes).
Click `Create Schedule` to generate the initial calendar.
### 2.	Moonlighting export (optional)
If any shifts remain uncovered, a `Moonlighting Shifts Export` button appears; click to download a CSV of open slots.
### 3.	Step 2 — Submit additional notes
Enter the requestor’s name, type a free-text note, and press **Submit**.

**Examples**

- “I can only cover **July 15 L2** and **L3**.”
- “Please swap my **August 3 L1** shift with **Alice**.”
- “My maximum for this month is **three shifts**.”

After submission, the calendar, legend, and all underlying data structures refresh automatically.

⸻

## 5 Customisation guidelines
- **Objective weights** – adjust values in `utils/schedule/objective.py`.
- **Additional hard constraints** – add `model.Add(...)` statements in `utils/schedule/scheduler.py`.
- **Model selection** – each `Agent` defines its OpenAI model via the `model=` argument (default **gpt-4o**).
- **Logging** – console output highlights discarded agent data and any auto-generated defaults.

⸻

## 6 Dependencies

The project runs using Python 3.9 + and relies on the following core packages:

| Package         | Purpose                                              |
|----------------|------------------------------------------------------|
| `openai`        | Access to GPT models for parsing tasks              |
| `google-ortools`| CP-SAT optimiser                                    |
| `streamlit`     | Web UI framework                                    |
| `pandas`        | CSV processing                                      |
| `python-dotenv` | Local `.env` management for `OPENAI_API_KEY` (optional) |
| `pytest` / `unittest` | Test execution (used by the scripts in `tests/`)   |
