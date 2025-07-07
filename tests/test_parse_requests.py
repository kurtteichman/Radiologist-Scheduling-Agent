from datetime import date, timedelta, datetime
from utils.schedule.scheduler import schedule_with_fallback_days_only
from utils.schedule.alterations import (
    update_monthly_caps,
    build_availability_matrix_from_changes,
    update_requested_shifts,
    update_assigned_shifts
)
from utils.parse.parse_requests import (
    extract_monthly_cap_updates,
    get_availability_flips,
    get_requested_shifts,
    get_assignment_edits
)
import asyncio

# ------------------------------------------------------------------------- #
# Helpers
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
# Full Test Script
# ------------------------------------------------------------------------- #

def simulate():
    start_date = date(2025, 7, 1)
    end_date = date(2025, 7, 31)
    schedule_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    schedule_entries = make_schedule_entries(schedule_dates)
    num_slots = len(schedule_entries)

    radiologists = [f"Rad_{i}" for i in range(8)]
    monthly_caps = {(i, "2025-07"): 10 for i in range(len(radiologists))}
    availability_matrix = [[1] * num_slots for _ in radiologists]
    requested_shift_map = {}

    initial_result = schedule_with_fallback_days_only(
        radiologists,
        schedule_entries,
        availability_matrix,
        monthly_caps,
    )
    final_schedule, assignments_by_emp, uncovered = initial_result
    print_result("Initial Schedule", initial_result)

    # Each test request
    requests = [
        ("I'd like to work 5 shifts in July.", "Dr. Singh"),
        ("I'm only free on July 7 L2 and L3.", "Dr. Singh"),
        ("Please assign me July 7 L2.", "Dr. Singh"),
        ("Can you swap July 10 L3 from Rad_1 to Rad_2?", "Rad_1")
    ]

    for note, name in requests:
        print(f"\n--- Processing note for {name or '[Unspecified Radiologist]'} ---")

        # 1. Monthly cap update
        cap_updates = asyncio.run(extract_monthly_cap_updates(
            note=note, name=name, year=start_date.year, month=start_date.month
        ))
        monthly_caps, radiologists, availability_matrix = update_monthly_caps(
            cap_updates, monthly_caps, radiologists, availability_matrix, default_availability_length=num_slots
        )
        print("✅ Monthly cap update successful:", cap_updates)

        # 2. Availability change
        flip_ops = asyncio.run(get_availability_flips(note, name, start_date.year))
        availability_matrix = build_availability_matrix_from_changes(flip_ops, availability_matrix, radiologists, schedule_entries)
        print("✅ Availability flip:", flip_ops)
        print("Availability Matrix # of Rows: ", len(availability_matrix))
        print("Availability Matrix: ", availability_matrix[-1])

        # 3. Requested shifts
        request_ops = asyncio.run(get_requested_shifts(note, name or "", start_date.year))
        requested_shift_map = update_requested_shifts(request_ops, requested_shift_map, radiologists)
        print("✅ Requested shifts:", request_ops)

        # 4. Assignment edits
        edit_ops = asyncio.run(get_assignment_edits(note, name, start_date=start_date, assignments_by_emp=assignments_by_emp))

        # 🔧 Ensure new radiologists are properly initialized
        involved_names = [edit.get("radiologist") for edit in edit_ops if "radiologist" in edit]
        for edit in edit_ops:
            if edit["action"] == "swap":
                involved_names.extend([edit["r1"], edit["r2"]])

        for r in set(involved_names):
            if r not in assignments_by_emp:
                assignments_by_emp[r] = []
            if r not in radiologists:
                radiologists.append(r)
                availability_matrix.append([1] * num_slots)
                monthly_caps[(radiologists.index(r), "2025-07")] = 5  # default cap

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
            final_schedule, assignments_by_emp, uncovered = schedule_with_fallback_days_only(
                radiologists,
                schedule_entries,
                availability_matrix,
                monthly_caps,
                requested_shift_map
            )
        print("✅ Assignment edit:", edit_ops)
        print_result("Final Schedule After Request", (final_schedule, assignments_by_emp, uncovered))

if __name__ == "__main__":
    simulate()