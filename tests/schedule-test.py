"""
unit_tests_scheduler.py  – quick sanity-checks for the *new* CP-SAT scheduler

All tests now use:

    • schedule_entries  – list[{"date": datetime.date, "shift": "L1|L2|L3"}]
    • monthly_caps      – hard upper-bounds per (employee_idx, "YYYY-MM")

The helper routines duplicate each daily rule to all three shifts,
so you don’t have to think about shift-level availability for these
simple cases.
"""

from datetime import date, timedelta

from utils.schedule.scheduler import schedule_with_fallback_days_only


# ------------------------------------------------------------------------- #
#  Helpers
# ------------------------------------------------------------------------- #
SHIFTS = ["L1", "L2", "L3"]


def make_schedule_entries(dates, shifts=SHIFTS):
    """Expand each date into three shift-slots."""
    return [
        {"date": d, "shift": sh}
        for d in dates
        for sh in shifts
    ]


def generate_availability_matrix(num_employees,
                                 schedule_entries,
                                 week_pattern=None,
                                 date_exclusion=None):
    """
    Build a (num_employees × num_slots) matrix.
    week_pattern – list[7] of 1/0 for Mon…Sun  (1 = can work)
    date_exclusion – iterable[date] of explicit no-work days
    """
    if date_exclusion is None:
        date_exclusion = set()
    else:
        date_exclusion = set(date_exclusion)

    matrix = []
    for _ in range(num_employees):
        row = []
        for se in schedule_entries:
            d = se["date"]
            ok = True
            if week_pattern is not None and not week_pattern[d.weekday()]:
                ok = False
            if d in date_exclusion:
                ok = False
            row.append(1 if ok else 0)
        matrix.append(row)
    return matrix

def build_weekday_based_row(forbidden_days):
    # forbidden_days = set of weekday integers (0=Mon, ..., 6=Sun)
    row = []
    for se in schedule_entries:
        weekday = se["date"].weekday()
        row.append(0 if weekday in forbidden_days else 1)
    return row

def print_result(label, result):
    final_schedule, assignments_by_emp, uncovered = result
    print(f"\n{label}")
    print("  assignments_by_emp:")
    for emp, slots in assignments_by_emp.items():
        print(f"    {emp}: {len(slots)} slots  -> {[f'{s['date']} {s['shift']}' for s in slots]}")
    print(f"  uncovered slots: {len(uncovered)}")


# ------------------------------------------------------------------------- #
#  Common date range
# ------------------------------------------------------------------------- #
start_date = date(2025, 6, 1)
end_date   = date(2025, 6, 7)
schedule_dates = [start_date + timedelta(days=i)
                  for i in range((end_date - start_date).days + 1)]
schedule_entries = make_schedule_entries(schedule_dates)
num_slots = len(schedule_entries)

employees = ["Alice", "Bob"]

# ------------------------------------------------------------------------- #
#  CASE 1 – two employees, full availability
# ------------------------------------------------------------------------- #
availability = [[1] * num_slots for _ in employees]
monthly_caps = {
    (0, "2025-06"): 3,
    (1, "2025-06"): 3,
}

print_result(
    "Test Case 1: Full Availability",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
    )
)

# ------------------------------------------------------------------------- #
#  CASE 2 – both cannot work on weekends
# ------------------------------------------------------------------------- #
availability = generate_availability_matrix(
    num_employees=2,
    schedule_entries=schedule_entries,
    week_pattern=[1, 1, 1, 1, 1, 0, 0],   # Sat/Sun = 0
)
print_result(
    "Test Case 2: No Weekend Availability",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
    )
)

# ------------------------------------------------------------------------- #
#  CASE 3 – alternating daily availability
# ------------------------------------------------------------------------- #
row_a = [(1 if (i // 3) % 2 == 0 else 0) for i in range(num_slots)]
row_b = [(0 if (i // 3) % 2 == 0 else 1) for i in range(num_slots)]
availability = [row_a, row_b]
monthly_caps = {
    (0, "2025-06"): 4,
    (1, "2025-06"): 3,
}
print_result(
    "Test Case 3: Alternating Availability",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
    )
)

# ------------------------------------------------------------------------- #
#  CASE 4 – only Alice partially available
# ------------------------------------------------------------------------- #
row_a = [1 if i < 9 else 0 for i in range(num_slots)]  # first 3 days (3 shifts/day)
row_b = [0] * num_slots
availability = [row_a, row_b]
monthly_caps = {
    (0, "2025-06"): 3,
    (1, "2025-06"): 3,
}
print_result(
    "Test Case 4: Single-Employee Partial Availability",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
    )
)

# ------------------------------------------------------------------------- #
#  CASE 5 – limited Alice availability (mid-week only)
# ------------------------------------------------------------------------- #

# First, filter slots to mid-week for Alice (e.g., June 3–5)
allowed_dates_alice = {date(2025, 6, 3), date(2025, 6, 4), date(2025, 6, 5)}

availability = []
for e in range(2):  # Alice, Bob
    row = []
    for se in schedule_entries:
        if e == 0:  # Alice
            row.append(1 if se["date"] in allowed_dates_alice else 0)
        else:  # Bob is fully available
            row.append(1)
    availability.append(row)

monthly_caps = {
    (0, "2025-06"): 3,
    (1, "2025-06"): 4,
}

print_result(
    "Test Case 5: Limited Alice Availability (Mid-Week Only)",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
    )
)

# ------------------------------------------------------------------------- #
#  CASE 6 – Full Example (Hardcoded from real CSVs)
# ------------------------------------------------------------------------- #
from datetime import date, timedelta
import pandas as pd

# 1. Build schedule_entries (from July 1 to 31, each day with L1–L3)
start_date = date(2025, 7, 1)
end_date = date(2025, 7, 31)
schedule_entries = []

for i in range((end_date - start_date).days + 1):
    current_date = start_date + timedelta(days=i)
    for shift in ["L1", "L2", "L3"]:
        schedule_entries.append({"date": current_date, "shift": shift})

num_slots = len(schedule_entries)
assert num_slots == 93  # 31 days × 3 shifts

# 2. Define employees (from radiologist_profiles.csv)
employees = [
    "Radiologist A", "Radiologist B", "Radiologist C", "Radiologist D",
    "Radiologist E", "Radiologist F", "Radiologist G", "Radiologist H"
]
num_employees = len(employees)

# 3. Define availability patterns
# A, B: weekdays only (Mon–Fri)
# C, D: exclude Friday and Saturday
# E–H: fully available
availability_matrix = []
for i in range(num_employees):
    row = []
    for se in schedule_entries:
        weekday = se["date"].weekday()
        if i < 2:
            row.append(1 if weekday < 5 else 0)  # No Sat/Sun
        elif i < 4:
            row.append(1 if weekday not in {4, 5} else 0)  # No Fri/Sat
        else:
            row.append(1)  # Fully available
    availability_matrix.append(row)

# 4. Hardcoded monthly caps (from radiologist_profiles.csv)
monthly_caps = {
    (0, "2025-07"): 10,  # A
    (1, "2025-07"): 12,  # B
    (2, "2025-07"): 8,  # C
    (3, "2025-07"): 14,  # D
    (4, "2025-07"): 7,  # E
    (5, "2025-07"): 10,  # F
    (6, "2025-07"): 16,  # G
    (7, "2025-07"): 5,  # H
}

# 5. Run scheduler
result = schedule_with_fallback_days_only(
    employees,
    schedule_entries,
    availability_matrix,
    monthly_caps,
)

print_result("Test Case 6: Full Example (Hardcoded from July CSV)", result)

# Setup
employees = ["Alice", "Bob"]
schedule_dates = [date(2025, 6, 1) + timedelta(days=i) for i in range(7)]
schedule_entries = make_schedule_entries(schedule_dates)
num_slots = len(schedule_entries)
availability = [[1] * num_slots for _ in employees]
monthly_caps = {(0, "2025-06"): 3, (1, "2025-06"): 3}

# Test Case 7a – Alice requests June 2 L2
requested_shift_map = {(0, date(2025, 6, 2), "L2"): 1}
result_7a = schedule_with_fallback_days_only(
    employees, schedule_entries, availability, monthly_caps, requested_shift_map=requested_shift_map
)
print_result("Test Case 7a: Alice requests June 2 L2", result_7a)

# Test Case 7b – Both request different days
requested_shift_map = {
    (0, date(2025, 6, 2), "L2"): 1,
    (1, date(2025, 6, 3), "L3"): 1,
}
result_7b = schedule_with_fallback_days_only(
    employees, schedule_entries, availability, monthly_caps, requested_shift_map=requested_shift_map
)
print_result("Test Case 7b: Both request different days", result_7b)

# Test Case 7c – Both request same day, different shifts
requested_shift_map = {
    (0, date(2025, 6, 2), "L2"): 1,
    (1, date(2025, 6, 2), "L3"): 1,
}
result_7c = schedule_with_fallback_days_only(
    employees, schedule_entries, availability, monthly_caps, requested_shift_map=requested_shift_map
)
print_result("Test Case 7c: Both request same day, different shifts", result_7c)

# Test Case 7d – Both request same shift
requested_shift_map = {
    (0, date(2025, 6, 2), "L2"): 1,
    (1, date(2025, 6, 2), "L2"): 1,
}
result_7d = schedule_with_fallback_days_only(
    employees, schedule_entries, availability, monthly_caps, requested_shift_map=requested_shift_map
)
print_result("Test Case 7d: Both request same exact shift", result_7d)

# ------------------------------------------------------------------------- #
#  CASE 8 – Weekend restrictions and two requests
# ------------------------------------------------------------------------- #
start_date = date(2025, 7, 1)
end_date = date(2025, 7, 31)
schedule_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
schedule_entries = make_schedule_entries(schedule_dates)
num_slots = len(schedule_entries)

employees = [
    "Radiologist 0", "Radiologist 1", "Radiologist 2", "Radiologist 3",
    "Radiologist 4", "Radiologist 5", "Radiologist 6", "Radiologist 7"
]

availability = [
    build_weekday_based_row({4, 5, 6}),  # R0: No Fri/Sat/Sun
    build_weekday_based_row({4, 5, 6}),  # R1: No Fri/Sat/Sun
    build_weekday_based_row({4, 5}),     # R2: No Fri/Sat
    build_weekday_based_row({4, 5}),     # R3: No Fri/Sat
    [1]*93,                              # R4: Fully available
    [1]*93,                              # R5: Fully available
    [1]*93,                              # R6: Fully available
    [1]*93,                              # R7: Fully available
]

monthly_caps = {
    (0, "2025-07"): 10,
    (1, "2025-07"): 12,
    (2, "2025-07"): 8,
    (3, "2025-07"): 14,
    (4, "2025-07"): 7,
    (5, "2025-07"): 10,
    (6, "2025-07"): 16,
    (7, "2025-07"): 5,
}

requested_shift_map = {
    (4, date(2025, 7, 15), "L2"): 1,  # Radiologist 4 requests July 15 L2
    (7, date(2025, 7, 23), "L1"): 1,  # Radiologist 7 requests July 23 L1
}

print_result(
    "Test Case 8: Weekend restrictions and two requests",
    schedule_with_fallback_days_only(
        employees,
        schedule_entries,
        availability,
        monthly_caps,
        requested_shift_map=requested_shift_map
    )
)