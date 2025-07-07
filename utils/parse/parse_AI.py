from agents import Agent, Runner
from datetime import datetime, timedelta
import json
import ast

# Agent for availability
availability_parser_agent = Agent(
    name="Availability Parser Agent",
    instructions="""
You are a scheduling assistant. Your job is to analyze a natural language statement about someone's availability and return a list of 1s and 0s — one number per shift — for a specified date range.

Rules:
- 1 means available, 0 means unavailable.
- Each day has three shifts: L1, L2, and L3 — in that order.
- The list must be **as long as the number of days × 3** in the date range (inclusive).
- Your response must be a **list** of 1s and 0s, like this:
    - Example (2 days):
        Input: '0: 2025-07-01 (Tuesday)', '1: 2025-07-02 (Wednesday)'; The employee has said: "Can cover any weekday or weekend shift. Unavailable for July 2 L1 and L3."
        List returned: [1, 1, 1, 0, 1, 0]
        Explanation: (Omitted in final output) — July 1: L1=1, L2=1, L3=1; July 2: L1=0, L2=1, L3=0
- Do not return anything other than the list. No explanation.
- If a radiologist requests a specific shift on a date, ensure their availability on that shift is set to 1, even if other availability patterns would exclude that time. Requests always override unavailability for that specific shift.
- If a note says “unavailable on [date]” mark all three shifts for that date as 0.
- If a note says “unavailable for [date] L2 and L3” mark only those specific shifts as 0.
- I need the output to be formatted so it can be parsed by json.loads without ANY additional symbols or characters
""",
    model="gpt-4o",
)

# Agent for extracting requested shifts
request_extraction_agent = Agent(
    name="Request Extraction Agent",
    instructions="""
You are a scheduling assistant. Your job is to extract any requested shifts from the following natural language availability note. You will be provided a list of dates with L1, L2, and L3 shifts.

Return a list of requested shifts in the form:
[
  {"date": "YYYY-MM-DD", "shift": "L1"},
  ...
]

If there are no explicit requests, return an empty list: []

Only include shifts that the employee **explicitly asked for** (e.g. "I would like to work July 2 L2"), or otherwise, if no shift is specified for a date WITH AN EXPLICIT REQUEST, choose ***only one shift at random*** to add.

Only respond with a list. Do not explain anything.
"""
)

def extract_list_from_output(output_str):
    try:
        result = json.loads(output_str)
    except json.JSONDecodeError:
        try:
            result = ast.literal_eval(output_str)
        except Exception:
            raise ValueError(f"Invalid format: {output_str}")
    if isinstance(result, list) and all(x in [0, 1] for x in result):
        return result
    raise ValueError(f"Expected list of 0s and 1s. Got: {output_str}")

def extract_json_from_output(output_str):
    import ast

    # Remove Markdown-style ``` wrappers if present
    if output_str.strip().startswith("```"):
        output_str = "\n".join(
            line for line in output_str.strip().splitlines()
            if not line.strip().startswith("```")
        )

    try:
        return json.loads(output_str)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(output_str)
        except Exception:
            raise ValueError(f"Invalid format: {output_str}")
    raise ValueError(f"Expected valid JSON. Got: {output_str}")

async def extract_availability_chunk(note, chunk_start, chunk_end):
    date_list = [
        f"{i}: {(chunk_start + timedelta(days=i)).strftime('%Y-%m-%d')} ({(chunk_start + timedelta(days=i)).strftime('%A')})"
        for i in range((chunk_end - chunk_start).days + 1)
    ]
    indexed_days = "\n".join(date_list)

    input_text = f"""
The employee has said: "{note}"

Below is a list of days in the schedule, indexed by position:

{indexed_days}

Please return a Python-style list of 0s and 1s, one per shift. Each day has 3 shifts: L1, L2, L3 (in that order).
"""
    runner = Runner()
    result = await runner.run(availability_parser_agent, input_text)
    return extract_list_from_output(result.final_output)

async def extract_requested_shifts(note, schedule_entries):
    """
    Returns: dict[(employee_idx, date, shift)] = 1
    """
    shift_list = [
        {"date": entry["date"].strftime("%Y-%m-%d"), "shift": entry["shift"]}
        for entry in schedule_entries
    ]
    shift_text = json.dumps(shift_list, indent=2)

    input_text = f"""
The employee has said: "{note}"

Here are all possible shifts:

{shift_text}

Which shifts has the employee explicitly requested?
"""
    runner = Runner()
    result = await runner.run(request_extraction_agent, input_text)
    parsed = extract_json_from_output(result.final_output)

    return parsed  # list of dicts

async def extract_availability_matrix(radiologist_df, start_date, end_date):
    availability_matrix = []
    requested_shift_map = {}

    schedule_entries = []
    for d in (start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)):
        for shift in ["L1", "L2", "L3"]:
            schedule_entries.append({"date": d, "shift": shift})

    for i in range(len(radiologist_df)):
        note = radiologist_df["Notes"].iloc[i]

        # Parse availability in 9-shift chunks (i.e., 3-day chunks)
        full_list = []
        total_days = (end_date - start_date).days + 1
        total_shifts = total_days * 3  # 3 shifts per day
        chunk_size_days = 3  # 3 days * 3 shifts = 9 shifts

        for chunk_start_day in range(0, total_days, chunk_size_days):
            cs = start_date + timedelta(days=chunk_start_day)
            if cs > end_date:
                break
            ce = min(end_date, cs + timedelta(days=chunk_size_days - 1))
            chunk_result = await extract_availability_chunk(note, cs, ce)
            full_list.extend(chunk_result)

        if len(full_list) != total_shifts:
            raise ValueError(f"Agent failed to produce correct shift-level availability list length: {len(full_list)} vs {total_shifts}")
        availability_matrix.append(full_list)

        # Extract requested shifts
        requested_list = await extract_requested_shifts(note, schedule_entries)
        for r in requested_list:
            req_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
            shift = r["shift"]
            requested_shift_map[(i, req_date, shift)] = 1

        print(f"\n➡️ {radiologist_df['Radiologist_ID'][i]}: {note}")
        print(f"📤 Availability: {availability_matrix[i]}")
        print(f"📤 Requests: {requested_shift_map}")

    return availability_matrix, requested_shift_map