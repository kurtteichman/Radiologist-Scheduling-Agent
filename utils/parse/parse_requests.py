from datetime import date, datetime
from agents import Agent, Runner
import json
import ast

from utils.schedule.alterations import build_availability_matrix_from_changes, update_assigned_shifts, update_monthly_caps, update_requested_shifts
from utils.schedule.scheduler import schedule_with_fallback_days_only


# Agent to detect and extract monthly cap change requests
monthly_cap_agent = Agent(
    name="Monthly Cap Agent",
    instructions="""
You are a scheduling assistant.

Your job is to extract shift cap updates from a radiologist's message. Some requests will include specific maximum shifts per month, while others will not.

Example 1: "I can cover up to 6 shifts."
Example 2: "I'll take 4 shifts."
Example 3: "The maximum number I can work this month is 2."
Example 4: "I can take 3 shifts."

Your output must be a list of dictionaries like this:
[
  {
    "name": "<Radiologist name>",
    "new_max": <integer>,
    "month": "YYYY-MM"
  }
]

Rules:
- If month is mentioned with no year, assume year = {year}.
- If someone says "this month", assume month = {month}, year = {year}.
- If no max shift number is mentioned, return [].
- DO NOT INCLUDE ANY EXTRA TEXT OR EXPLANATIONS
""",
)

availability_change_agent = Agent(
    name="Availability Change Agent",
    instructions="""
You are an assistant that extracts AVAILABILITY changes from a radiologist's message.

Your job is to read the note and return a list of flips to the availability matrix, in this format:
[
  {
    "name": "Radiologist_Name",
    "flips": [
      {"date": "YYYY-MM-DD", "shift": "L1", "available": true},
      ...
    ]
  }
]

Rules:
- If the message says the radiologist is ONLY available for certain days/shifts, assume all OTHER shifts are NOT available.
- If the message says the radiologist is unavailable on a certain day/shift, set available to FALSE for just those.
- If a radiologist specifies that they ***are*** available on given dates or ranges, set all relevant day(s) to TRUE and ONLY for relevant days.
- Always use shift names like "L1", "L2", "L3".
- If the year is not mentioned, assume it is {YEAR}.
- If no availability changes are described, return an empty list: []
- Do NOT include preferred or requested shifts here — this is only for availability.

Example:
Message: "I'm only available on July 7 for L2 and L3" (Referencing all of July, but ***PLEASE LOOK AT ALL DATES IN DATE RANGE***)
Output:
[
  {
    "name": "Dr. Smith",
    "flips": [
      .
      .
      .
      {"date": "2025-07-06", "shift": "L2", "available": false},
      {"date": "2025-07-06", "shift": "L3", "available": false},
      {"date": "2025-07-07", "shift": "L1", "available": false},
      {"date": "2025-07-07", "shift": "L2", "available": true},
      {"date": "2025-07-07", "shift": "L3", "available": true},
      {"date": "2025-07-08", "shift": "L1", "available": false},
      {"date": "2025-07-08", "shift": "L2", "available": false},
      .
      .
      .
      {"date": "2025-07-31", "shift": "L2", "available": false},
      {"date": "2025-07-31", "shift": "L3", "available": false}
    ]
  }
]

DO NOT INCLUDE ANY EXTRA TEXT OR EXPLANATIONS
"""
)

requested_shift_agent = Agent(
    name="Requested Shifts Agent",
    instructions="""
You are a scheduling assistant. Extract explicitly requested shifts from the message.

Example 1: "I would like to request the November 15 L2 shift."
Example 2: "May I please take the January 2 L3 shift please?"
Example 3: "I'll take 2 shifts this month. Can one of them be the March 5 L1 shift please?"
Example 4: "I can work on February 2nd if those spots need to be filled" ==> See the empty slots on February 2 and request all empty shifts

Return a list of requests in the form:
[
  {
    "name": "<Radiologist_Name>",
    "action": "add",
    "shifts": [
      {"date": "YYYY-MM-DD", "shift": "L2"},
      ...
    ]
  }
]

If no shifts are requested, return an empty list.
Do NOT include availability changes here.

Important rules:
- Replace "<Radiologist_Name>" with the actual radiologist name if it is known or provided.
- If the year is not specified in the message, assume it is the current year.
- If the message says something like “July 7,” and today is June 2025, assume “2025-07-07”.
- Only include date–shift pairs that are clearly requested.
- DO NOT INCLUDE ANY EXTRA TEXT OR EXPLANATIONS
"""
)

assignment_change_agent = Agent(
    name="Assignment Update Agent",
    instructions="""
You are a scheduling assistant. Based on the radiologist's message, determine any direct assignment modifications.

Valid actions include:
- add: add a radiologist to a shift
- remove: remove a radiologist from a shift
- swap: move a shift from one radiologist to another (should only be performed when ***explicitly*** specified e.g. "I want to give my spot on August 1 to Employee X" or "I want to swap my April 1 shift with Employee Y")

Return a list of dictionaries in one of the following formats:
- {"action": "add", "radiologist": "<Name>", "date": "YYYY-MM-DD", "shift": "L1"}
- {"action": "remove", "radiologist": "<Name>", "date": "YYYY-MM-DD", "shift": "L2"}
- {"action": "swap", "r1": "Alice", "r2": "Bob", "date": "YYYY-MM-DD", "shift": "L3"}

Always return a list, even if only one item or empty. DO NOT INCLUDE ANY EXTRA TEXT OR EXPLANATIONS
"""
)

def strip_code_fences(s: str) -> str:
    """
    Removes leading/trailing triple backtick fences (e.g., ```json).
    """
    if s.startswith("```"):
        lines = s.strip().splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            return "\n".join(lines[1:-1]).strip()
    return s.strip()

# ---------------------------- RUNNER FUNCTIONS ---------------------------- #

def print_result(label, result):
    final_schedule, assignments_by_emp, uncovered = result
    print(f"\n{label}")
    print("  assignments_by_emp:")
    for emp, slots in assignments_by_emp.items():
        slot_strs = [f"{s['date']} {s['shift']}" for s in slots]
        print(f"    {emp}: {len(slots)} slots -> {slot_strs}")
    print(f"  uncovered slots: {len(uncovered)}")

def parse_json_list(output_str: str):
    try:
        # Remove triple backticks and language specifier if present
        cleaned = (
            output_str.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        return json.loads(cleaned)
    except Exception:
        try:
            return ast.literal_eval(cleaned)
        except Exception:
            raise ValueError(f"Invalid agent output: {output_str}")

async def get_availability_flips(note: str, name: str | None = None, default_year: int | None = None):
    runner = Runner()

    prefix = ""
    if name:
        prefix += f"Radiologist Name: {name}\nDefault year: {default_year}"

    full_input = prefix + note
    result = await runner.run(availability_change_agent, full_input)
    return parse_json_list(result.final_output.strip())

async def get_requested_shifts(note: str, name: str = "", default_year: int = None):
    prompt = f"""
Radiologist: {name}
Note: "{note}"

Extract explicitly requested shifts from the message.

Return a list of requests in the form:
[
  {{
    "name": "{name}",
    "action": "add",
    "shifts": [
      {{"date": "{default_year}-MM-DD", "shift": "L2"}},
      ...
    ]
  }}
]

Rules:
- If a date is mentioned without a year, assume the year is {default_year}.
- If no shifts are requested, return an empty list.
- Do NOT include availability changes here.
"""
    runner = Runner()
    result = await runner.run(requested_shift_agent, prompt)
    return parse_json_list(result.final_output)

async def get_assignment_edits(
    note: str,
    name: str = None,
    start_date: date = None,
    assignments_by_emp: dict = None
):
    if start_date is None:
        start_date = date.today()
    fallback_year = start_date.year

    prompt = f"""
Radiologist: {name or 'Unknown'}
Note: "{note}"

Extract assignment change operations. If a date is mentioned without a year or with an incorrect year, assume the year is {fallback_year}.

Here are the current employee assignments: {assignments_by_emp}

Return a list in this format:
[
  {{
    "action": "swap",
    "r1": "Rad_1",
    "r2": "Rad_2",
    "date": "{fallback_year}-MM-DD",
    "shift": "L3"
  }}
]
"""

    runner = Runner()
    result = await runner.run(assignment_change_agent, prompt)

    output_str = result.final_output.strip()

    # Remove ```json or ``` wrappers if present
    for marker in ["```json", "```"]:
        if output_str.startswith(marker) and output_str.endswith("```"):
            output_str = output_str[len(marker):-3].strip()

    try:
        edits = json.loads(output_str)
    except Exception:
        try:
            edits = ast.literal_eval(output_str)
        except Exception:
            raise ValueError(f"Invalid agent output: {output_str}")

    # Fix malformed or missing year in dates, and update placeholder name
    for edit in edits:
        if "date" in edit and isinstance(edit["date"], str):
            parts = edit["date"].split("-")
            if parts[0] == "YYYY" or not parts[0].isdigit():
                edit["date"] = f"{fallback_year}-{parts[1]}-{parts[2]}"

        if "name" in edit and edit["name"] == "Radiologist_Name" and name:
            edit["name"] = name

    return edits

async def extract_monthly_cap_updates(note: str, name: str | None = None, year: int | None = None, month: int | None = None, names: list | None = []):
    from agents import Runner
    runner = Runner()

    # Add name/month context if they exist
    prefix = ""
    if name:
        prefix += f"Radiologist Name: {name}\n"
    if year and month:
        prefix += f"Target Month: {year:04d}-{month:02d}\n"
    if names:
        prefix += f"Current Employees: {names}\n"

    full_input = prefix + note

    result = await runner.run(monthly_cap_agent, full_input)
    output_str = result.final_output.strip()

    print(f"Raw agent output:\n{output_str}")

    return parse_json_list(output_str)

async def process_note_against_schedule(note, name, start_date, availability_matrix, assignments_by_emp, requested_shift_map, monthly_caps, schedule_entries, final_schedule):
    num_slots = len(schedule_entries)
    uncovered = []
    radiologists = list(assignments_by_emp.keys())

    cap_updates = await extract_monthly_cap_updates(note, name, start_date.year, start_date.month, radiologists)
    monthly_caps, radiologists, availability_matrix = update_monthly_caps(
        cap_updates, monthly_caps, radiologists, availability_matrix, default_availability_length=num_slots
    )
    print("✅ Monthly cap update successful:", cap_updates)
    
    flip_ops = await get_availability_flips(note, name, default_year=start_date.year)
    availability_matrix = build_availability_matrix_from_changes(flip_ops, availability_matrix, radiologists, schedule_entries)
    print("✅ Availability flip:", flip_ops)
    print("Availability Matrix # of Rows: ", len(availability_matrix))
    # print("Availability Matrix: ", availability_matrix[-1])
    
    request_ops = await get_requested_shifts(note, name, start_date.year)
    requested_shift_map = update_requested_shifts(request_ops, requested_shift_map, radiologists)
    print("✅ Requested shifts:", request_ops)

    for rad in radiologists:
        if rad not in assignments_by_emp:
            assignments_by_emp[rad] = []

    radiologists = list(assignments_by_emp.keys())

    edit_ops = await get_assignment_edits(note, name, start_date, assignments_by_emp)
    # Ensure any new names in edit_ops are accounted for
    for edit in edit_ops:
        involved = []
        if edit["action"] == "swap":
            involved = [edit["r1"], edit["r2"]]
        elif edit["action"] in {"add", "remove"}:
            involved = [edit["radiologist"]]
        for r in involved:
            if r not in assignments_by_emp:
                print(f"🆕 Detected new radiologist in edit: {r} — initializing")
                assignments_by_emp[r] = []
                if r not in radiologists:
                    radiologists.append(r)
                if len(availability_matrix) < len(radiologists):
                    availability_matrix.append([1] * len(schedule_entries))
            # 🛡️ Ensure monthly cap is set for new radiologists
        month_str = f"{start_date.year}-{start_date.month:02d}"
        for r in involved:
            idx = radiologists.index(r)
            cap_key = (idx, month_str)
            if cap_key not in monthly_caps:
                monthly_caps[cap_key] = 5  # default cap
    final_schedule, assignments_by_emp, uncovered = update_assigned_shifts(
            edits=edit_ops,
            final_schedule=final_schedule,
            assignments_by_emp=assignments_by_emp,
            uncovered_slots=uncovered,
            schedule_entries=schedule_entries,
            availability_matrix=availability_matrix,
            requested_shift_map=requested_shift_map,
            monthly_caps=monthly_caps,
            employees=radiologists
        )
    
    if not edit_ops:
        print("🧪 Checking requested_shift_map keys:")
        for k in requested_shift_map:
            if not (isinstance(k, tuple) and len(k) == 3):
                print(f"❌ Invalid key in requested_shift_map: {k}")
            else:
                print(f"✅ Valid key: {k}")
        final_schedule, assignments_by_emp, uncovered = schedule_with_fallback_days_only(radiologists, schedule_entries, availability_matrix, monthly_caps, requested_shift_map)
    print("✅ Assignment edit:", edit_ops)
    print_result("Final Schedule After Request", (final_schedule, assignments_by_emp, uncovered))

    return (
        final_schedule,
        assignments_by_emp,
        uncovered,
        availability_matrix,
        requested_shift_map,
        monthly_caps,
        radiologists,
    )
