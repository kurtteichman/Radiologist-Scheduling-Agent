# scheduler.py  (TOP OF FILE)

from __future__ import annotations
from ortools.sat.python import cp_model

# ⬇️  use *relative* imports so Python sees sibling modules
from .variables import (                       # CHANGED
    define_assignment_vars,
    define_coverage_vars,
    define_spacing_deviation_vars,
    define_day_overlap_penalty,
    define_multi_shift_penalties,
    define_requested_shift_vars
)
from .objective import build_objective         # CHANGED


# --------------------------------------------------------------------------- #
#  PUBLIC API  (minimally renamed)
# --------------------------------------------------------------------------- #
def schedule_with_fallback_days_only(
    employees,
    schedule_entries,                     # list[{date, shift}]
    availability_matrix,
    monthly_caps,                         # {(emp_idx,"YYYY-MM"): int}
    requested_shift_map=None
):
    """
    Returns (final_schedule, assignments_by_emp, uncovered_slots)

    *final_schedule* parallels schedule_entries (value = employee name | None)
    """
    model = cp_model.CpModel()
    E = len(employees)
    S = len(schedule_entries)

    # 1. decision vars
    a = define_assignment_vars(E, S, model)

    # ⛔ Enforce hard availability: cannot assign if unavailable
    for (e, s), var in a.items():
        if availability_matrix[e][s] == 0:
            model.Add(var == 0)

    # ⛔ REMOVE unavailability penalties — no longer needed
    # p = define_unavailability_penalty_vars(availability_matrix, a, model)

    c = define_coverage_vars(E, S, a, model)
    spacing_vars = define_spacing_deviation_vars(schedule_entries, a, monthly_caps, model)
    inter_day_overlap_penalties = define_day_overlap_penalty(schedule_entries, a, model)
    multi_shift_penalties = define_multi_shift_penalties(schedule_entries, a, model)
    request_penalties = define_requested_shift_vars(schedule_entries, a, requested_shift_map or {}, model)

    # 2. “At-most-one” employee per slot
    for s in range(S):
        model.Add(sum(a[e, s] for e in range(E)) <= 1)

    # 3. Hard monthly caps
    for (e, ym), cap in monthly_caps.items():
        slots = [
            s for s, se in enumerate(schedule_entries)
            if se["date"].strftime("%Y-%m") == ym
        ]
        model.Add(sum(a[e, s] for s in slots) <= cap)

    # 4. Objective: remove unavailability penalties since now hard
    build_objective(model, c, spacing_vars, inter_day_overlap_penalties, multi_shift_penalties, request_penalties)
    # 5. Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)

    # 6. Extract
    final_schedule = []
    for s in range(S):
        assigned = None
        for e in range(E):
            if solver.BooleanValue(a[e, s]):
                assigned = employees[e]
                break
        final_schedule.append(assigned)

    assignments_by_emp = {emp: [] for emp in employees}
    for s, assignee in zip(range(S), final_schedule):
        if assignee is not None:
            assignments_by_emp[assignee].append(schedule_entries[s])

    uncovered_slots = [
        schedule_entries[s]
        for s in range(S)
        if solver.BooleanValue(c[s]) == 0
    ]

    return final_schedule, assignments_by_emp, uncovered_slots