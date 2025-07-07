# tests/test_alterations.py

from datetime import date, timedelta
from utils.schedule.scheduler import schedule_with_fallback_days_only
from utils.schedule.alterations import (
    update_monthly_caps,
    flip_availability,
    update_requested_shifts,
    update_assigned_shifts
)

# ------------------------------------------------------------------------- #
#  Helpers
# ------------------------------------------------------------------------- #
SHIFTS = ["L1", "L2", "L3"]

def make_schedule_entries(dates, shifts=SHIFTS):
    return [{"date": d, "shift": sh} for d in dates for sh in shifts]

def print_result(label, result):
    final_schedule, assignments_by_emp, uncovered = result
    print(f"\n{label}")
    print("  assignments_by_emp:")
    for emp, slots in assignments_by_emp.items():
        slot_strs = [f"{s['date']} {s['shift']}" for s in slots]
        print(f"    {emp}: {len(slots)} slots -> {slot_strs}")
    print(f"  uncovered slots: {len(uncovered)}")

# ------------------------------------------------------------------------- #
#  Test Runner
# ------------------------------------------------------------------------- #
def run_tests():
    start_date = date(2025, 6, 1)
    end_date = date(2025, 6, 3)
    schedule_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    schedule_entries = make_schedule_entries(schedule_dates)
    num_slots = len(schedule_entries)
    employees = ["Alice", "Bob"]

    availability = [[1] * num_slots for _ in employees]
    monthly_caps = {(0, "2025-06"): 3, (1, "2025-06"): 3}
    requested_shift_map = {}

    # Initial schedule
    result = schedule_with_fallback_days_only(employees, schedule_entries, availability, monthly_caps)
    final_schedule, assignments_by_emp, uncovered = result
    print_result("Initial Schedule", result)

    # Add Charlie to caps
    cap_requests = [{"name": "Charlie", "new_max": 2, "month": "2025-06"}]
    monthly_caps, employees, availability = update_monthly_caps(
        cap_requests, monthly_caps, employees, availability, default_availability_length=num_slots
    )


    # Charlie is only available for one shift
    avail_requests = [{
        "name": "Charlie",
        "flips": [{
            "date": schedule_entries[0]["date"].isoformat(),  # Use string format
            "shift": schedule_entries[0]["shift"]
        }]
    }]
    availability = flip_availability(avail_requests, availability, employees, schedule_entries)


    # Charlie requests that one shift
    request_ops = [{
        "name": "Charlie",
        "action": "add",
        "shifts": [{
            "date": schedule_entries[0]["date"],
            "shift": "L2"
        }]
    }]
    requested_shift_map = update_requested_shifts(request_ops, requested_shift_map, employees)

    # Reoptimize with Charlie
    result = update_assigned_shifts(
        edits=[{"action": "reoptimize"}],
        employees=employees,
        schedule_entries=schedule_entries,
        availability_matrix=availability,
        monthly_caps=monthly_caps,
        requested_shift_map=requested_shift_map,
        final_schedule=final_schedule,
        assignments_by_emp=assignments_by_emp,
        uncovered_slots=uncovered,
    )

    print_result("Final Schedule After All Updates", result)

if __name__ == "__main__":
    run_tests()