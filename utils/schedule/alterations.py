from typing import List, Dict, Optional, Tuple
from datetime import date, datetime
from .scheduler import schedule_with_fallback_days_only



def update_monthly_caps(
    requests: List[Dict[str, str]],
    monthly_caps: Dict[Tuple[int, str], int],
    radiologist_names: List[str],
    availability_matrix: List[List[int]],
    default_availability_length: int
) -> Tuple[Dict[Tuple[int, str], int], List[str], List[List[int]]]:
    """
    Modifies monthly_caps in-place. Adds radiologists and availability if new.

    Args:
        requests: List of dicts with keys 'name', 'new_max', 'month'
        monthly_caps: Dict mapping (radiologist index, 'YYYY-MM') to int
        radiologist_names: List of radiologist names
        availability_matrix: List of availability lists per radiologist
        default_availability_length: Length of the shift list to initialize new availability

    Returns:
        Tuple containing updated (monthly_caps, radiologist_names, availability_matrix)
    """
    for r in requests:
        name = r["name"]
        cap = r["new_max"]
        month = r["month"]

        if name not in radiologist_names:
            idx = len(radiologist_names)
            radiologist_names.append(name)
            availability_matrix.append([1] * default_availability_length)
        else:
            idx = radiologist_names.index(name)

        monthly_caps[(idx, month)] = cap

    return monthly_caps, radiologist_names, availability_matrix


def build_availability_matrix_from_changes(
    changes: List[Dict],
    availability_matrix: List[List[int]],
    radiologist_names: List[str],
    schedule_entries: List[Dict[str, date]]
) -> List[List[int]]:
    """
    Update the availability_matrix in-place using explicitly provided True/False availability
    for specific (date, shift) combinations for each radiologist.

    Args:
        changes: List of dicts with 'name' and 'flips' (with 'date', 'shift', 'available')
        availability_matrix: The current matrix (will be modified)
        radiologist_names: Ordered list of radiologist names
        schedule_entries: List of schedule entries with 'date' and 'shift'

    Returns:
        Updated availability_matrix
    """
    # Build lookup: (date, shift) → column index
    shift_to_index = {
        (entry["date"], entry["shift"]): i
        for i, entry in enumerate(schedule_entries)
    }

    for change in changes:
        name = change["name"]
        flips = change["flips"]

        if name not in radiologist_names:
            print(f"⚠️ Skipping unknown radiologist: {name}")
            continue

        idx = radiologist_names.index(name)

        for flip in flips:
            try:
                date_val = flip["date"]
                shift = flip["shift"]
                available = flip.get("available", True)

                # Parse string date if needed
                if isinstance(date_val, str):
                    date_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
                else:
                    date_obj = date_val

                key = (date_obj, shift)
                shift_idx = shift_to_index.get(key)

                if shift_idx is not None:
                    availability_matrix[idx][shift_idx] = int(available)
                else:
                    print(f"⚠️ Shift not found in schedule: {key}")

            except Exception as e:
                print("❌ Error processing flip:", e)
                continue

    return availability_matrix

def update_requested_shifts(
    changes: List[Dict[str, any]],
    requested_shift_map: Dict[Tuple[int, date, str], int],
    radiologist_names: List[str]
) -> Dict[Tuple[int, date, str], int]:
    """
    Applies a list of changes to the requested shift map.

    Each change must include:
        - name: the radiologist name
        - action: 'add' or 'remove'
        - shifts: list of {"date": ..., "shift": ...}

    Returns:
        Updated requested_shift_map
    """
    for change in changes:
        name = change["name"]
        action = change["action"]
        shifts = change["shifts"]
        if name not in radiologist_names:
            continue
        idx = radiologist_names.index(name)

        for shift in shifts:
            # 🛠️ Normalize date string to datetime.date
            date_val = shift["date"]
            if isinstance(date_val, str):
                date_val = datetime.strptime(date_val, "%Y-%m-%d").date()
            key = (idx, date_val, shift["shift"])
            if action == "add":
                requested_shift_map[key] = 1
            elif action == "remove":
                requested_shift_map.pop(key, None)

    return requested_shift_map

def update_assigned_shifts(
    edits: List[Dict],
    final_schedule: List[Optional[str]],
    assignments_by_emp: Dict[str, List[Dict]],
    uncovered_slots: List[Dict],
    schedule_entries: List[Dict],
    availability_matrix: List[List[int]],
    requested_shift_map: Dict[Tuple[int, datetime.date, str], int],
    monthly_caps: Dict[Tuple[int, str], int],
    employees: List[str]
) -> Tuple[List[Optional[str]], Dict[str, List[Dict]], List[Dict]]:
    """
    Applies assignment edits to the current shift allocation.
    If a reoptimization flag is present, triggers full schedule recomputation.

    Args:
        edits: Either list of edit dicts or a single dict with {"action": "reoptimize"}
        final_schedule: List of names (or None) for each shift slot
        assignments_by_emp: Dict mapping employee to their assigned shift entries
        uncovered_slots: List of unfilled shift entries
        schedule_entries: All remaining unassigned shift entries
        availability_matrix: 2D list of availability
        requested_shift_map: Dict of explicit requests
        monthly_caps: Dict of (index, 'YYYY-MM') → max shifts
        radiologist_names: List of names corresponding to matrix indices

    Returns:
        Updated (final_schedule, assignments_by_emp, uncovered_slots)
    """
    # print(edits)

    for edit in edits:
        action = edit.get("action")

        if action == "swap":
            r1 = edit["r1"]
            r2 = edit["r2"]
            date = datetime.strptime(edit["date"], "%Y-%m-%d").date()
            shift = edit["shift"]

            # 1. Update assignments_by_emp
            assignments_by_emp[r1] = [
                se for se in assignments_by_emp[r1]
                if not (se["date"] == date and se["shift"] == shift)
            ]
            assignments_by_emp[r2].append({"date": date, "shift": shift})

            # 2. Update final_schedule
            for i, se in enumerate(schedule_entries):
                if se["date"] == date and se["shift"] == shift:
                    final_schedule[i] = r2
                    break

            # 3. Update requested_shift_map
            r1_idx = employees.index(r1) if r1 in employees else None
            r2_idx = employees.index(r2) if r2 in employees else None

            # Remove old request
            if r1_idx is not None:
                key = (r1_idx, date, shift)
                requested_shift_map.pop(key, None)

            # Add new request
            if r2_idx is not None:
                key = (r2_idx, date, shift)
                requested_shift_map[key] = 1

        elif action == "remove":
            r = edit["radiologist"]
            date = datetime.strptime(edit["date"], "%Y-%m-%d").date()
            shift = edit["shift"]

            # Remove from assignments
            assignments_by_emp[r] = [
                se for se in assignments_by_emp[r]
                if not (se["date"] == date and se["shift"] == shift)
            ]

            # Update final_schedule and uncovered_slots
            for i, se in enumerate(schedule_entries):
                if se["date"] == date and se["shift"] == shift:
                    final_schedule[i] = None
                    uncovered_slots.append(se)
                    break

            # Update availability_matrix to mark as unavailable
            if r in employees:
                r_idx = employees.index(r)
                for i, se in enumerate(schedule_entries):
                    if se["date"] == date and se["shift"] == shift:
                        availability_matrix[r_idx][i] = 0
                        break

        elif action == "add":
            r = edit["radiologist"]
            date = datetime.strptime(edit["date"], "%Y-%m-%d").date()
            shift = edit["shift"]

            if r not in employees:
                employees.append(r)
                # 🛡️ Ensure cap exists for this radiologist
            r_idx = employees.index(r)
            month_str = datetime.now().strftime("%Y-%m")  # or pass in explicitly
            cap_key = (r_idx, month_str)
            if cap_key not in monthly_caps:
                monthly_caps[cap_key] = 5
            if r not in assignments_by_emp:
                assignments_by_emp[r] = []
            if len(employees) > len(availability_matrix):
                availability_matrix.append([1]*len(schedule_entries))

            # Check if the radiologist already has this shift
            if any(s["date"] == date and s["shift"] == shift for s in assignments_by_emp.get(r, [])):
                continue  # Skip to avoid duplicate

            for i, se in enumerate(schedule_entries):
                if se["date"] == date and se["shift"] == shift:
                    if final_schedule[i] is not None:
                        break  # Slot is already filled by someone else

                    # Assign shift
                    final_schedule[i] = r
                    assignments_by_emp[r].append({"date": date, "shift": shift})
                    if se in uncovered_slots:
                        uncovered_slots.remove(se)

                    # Add to requested_shift_map
                    if r in employees:
                        r_idx = employees.index(r)
                        key = (r_idx, date, shift)
                        requested_shift_map[key] = 1

    return final_schedule, assignments_by_emp, uncovered_slots
