"""
variables.py – decision-variable helpers
"""

from ortools.sat.python import cp_model


# --------------------------------------------------------------------------- #
#  Primary assignment variables
# --------------------------------------------------------------------------- #
def define_assignment_vars(num_employees: int,
                           num_slots: int,
                           model: cp_model.CpModel):
    """
    BoolVar (e,s) == 1  ⇢  employee *e* is assigned to slot *s*
    """
    return {
        (e, s): model.NewBoolVar(f"a_e{e}_s{s}")
        for e in range(num_employees)
        for s in range(num_slots)
    }


# --------------------------------------------------------------------------- #
#  Penalty for assigning on a declared-unavailable slot
# --------------------------------------------------------------------------- #
def define_unavailability_penalty_vars(availability_matrix,
                                       assignment_vars,
                                       model: cp_model.CpModel):
    """
    For every (e,s) where availability==0, create a Bool that copies assignment.
    """
    penalty_vars = []
    for (e, s), assign in assignment_vars.items():
        if availability_matrix[e][s] == 0:
            p = model.NewBoolVar(f"penalty_e{e}_s{s}")
            model.Add(p == assign)
            penalty_vars.append(p)
    return penalty_vars


# --------------------------------------------------------------------------- #
#  NEW: coverage indicator  (anyone assigned to slot s?)
# --------------------------------------------------------------------------- #
def define_coverage_vars(num_employees: int,
                         num_slots: int,
                         assignment_vars,
                         model: cp_model.CpModel):
    coverage = {}
    for s in range(num_slots):
        c = model.NewBoolVar(f"covered_s{s}")
        model.Add(sum(assignment_vars[e, s] for e in range(num_employees)) == c)
        coverage[s] = c
    return coverage


# --------------------------------------------------------------------------- #
#  NEW: cluster (spacing) penalty  – minimise back-to-back shifts
# --------------------------------------------------------------------------- #
def define_spacing_deviation_vars(schedule_entries,
                                   assignment_vars,
                                   monthly_caps,
                                   model):
    """
    For each employee, penalize deviations from ideal spacing.
    This is softer and more general than fixed cluster windows.
    """
    from collections import defaultdict

    dates = [se["date"] for se in schedule_entries]
    emp_to_slots = defaultdict(list)
    num_employees = max(e for e, _ in assignment_vars) + 1

    for e in range(num_employees):
        for s in range(len(schedule_entries)):
            emp_to_slots[e].append((s, dates[s]))

    deviation_penalties = []
    for (e, ym), cap in monthly_caps.items():
        # Only slots within this month
        slots_this_month = [(s, d) for s, d in emp_to_slots[e]
                            if d.strftime("%Y-%m") == ym]
        if cap <= 1:
            continue  # can't space 1 shift

        slots_this_month = [
            (i, s["date"].month * 31 + s["date"].day)
            for i, s in enumerate(schedule_entries)
            if s["date"].strftime("%Y-%m") == ym
            and (e, i) in assignment_vars
        ]

        if not slots_this_month:
            continue  # skip if no assignments possible for this employee-month
        
        # Ideal spacing (in days)
        first = min(d for _, d in slots_this_month)
        last = max(d for _, d in slots_this_month)
        span = (last - first) + 1
        ideal_gap = span // max(1, cap - 1)

        # Penalize too-small gaps between any two assigned shifts
        for i in range(len(slots_this_month)):
            for j in range(i + 1, len(slots_this_month)):
                s1, d1 = slots_this_month[i]
                s2, d2 = slots_this_month[j]
                gap_days = abs(d2 - d1)  # ✅ both are integers

                # Create penalty var if gap is smaller than ideal
                if gap_days < ideal_gap:
                    z = model.NewBoolVar(f"gap_e{e}_s{s1}_s{s2}")
                    model.AddBoolAnd([assignment_vars[e, s1],
                                      assignment_vars[e, s2]]).OnlyEnforceIf(z)
                    model.AddBoolOr([assignment_vars[e, s1].Not(),
                                     assignment_vars[e, s2].Not()]).OnlyEnforceIf(z.Not())
                    deviation_penalties.append(z)

    return deviation_penalties

def define_day_overlap_penalty(schedule_entries,
                                assignment_vars,
                                model):
    from collections import defaultdict

    # Step 1: Group slot indices by date (regardless of shift)
    date_to_slots = defaultdict(list)
    for s, se in enumerate(schedule_entries):
        date_to_slots[se["date"]].append(s)

    num_employees = max(e for e, _ in assignment_vars) + 1
    overlap_vars = []

    for d, slots_on_day in date_to_slots.items():
        working_today_flags = []  # ⬅️ keep separate from the slot list

        # For each employee: are they working *any* shift that day?
        for e in range(num_employees):
            flags = [assignment_vars[e, s] for s in slots_on_day]
            if not flags:
                continue
            is_working_today = model.NewBoolVar(f"works_{d}_e{e}")
            model.AddMaxEquality(is_working_today, flags)
            working_today_flags.append(is_working_today)

        # Sum employees working this day
        count = model.NewIntVar(0, num_employees, f"workers_on_{d}")
        model.Add(count == sum(working_today_flags))

        # Penalize if >1 employee is scheduled that day
        overlap_penalty = model.NewBoolVar(f"overlap_day_{d}")
        model.Add(count > 1).OnlyEnforceIf(overlap_penalty)
        model.Add(count <= 1).OnlyEnforceIf(overlap_penalty.Not())
        overlap_vars.append(overlap_penalty)

    return overlap_vars

def define_multi_shift_penalties(schedule_entries,
                                  assignment_vars,
                                  model):
    """
    For each (employee, date), add a BoolVar that fires if they are assigned
    to 2+ shifts that day. Used as a soft penalty.
    """
    from collections import defaultdict

    num_employees = max(e for e, _ in assignment_vars) + 1
    emp_date_to_slots = defaultdict(list)

    for (e, s), var in assignment_vars.items():
        d = schedule_entries[s]["date"]
        emp_date_to_slots[(e, d)].append(var)

    multi_shift_penalties = []
    for (e, d), shift_vars in emp_date_to_slots.items():
        if len(shift_vars) <= 1:
            continue

        count = model.NewIntVar(0, len(shift_vars), f"num_shifts_e{e}_{d}")
        model.Add(count == sum(shift_vars))

        # Penalize if count > 1
        penalty = model.NewBoolVar(f"multi_shift_e{e}_{d}")
        model.Add(count > 1).OnlyEnforceIf(penalty)
        model.Add(count <= 1).OnlyEnforceIf(penalty.Not())
        multi_shift_penalties.append(penalty)

    return multi_shift_penalties

def define_requested_shift_vars(schedule_entries, assignment_vars, requested_map, model):
    request_penalties = []

    # First, group requests by (date, shift)
    from collections import defaultdict
    request_groups = defaultdict(list)
    for (e, d, sh), val in requested_map.items():
        if val:
            request_groups[(d, sh)].append(e)

    for idx, se in enumerate(schedule_entries):
        d = se["date"]
        sh = se["shift"]
        key = (d, sh)
        if key not in request_groups:
            continue

        requesters = request_groups[key]

        if len(requesters) == 1:
            # Hard constraint: exactly one requester, must be assigned
            e = requesters[0]
            assign_var = assignment_vars[(e, idx)]
            model.Add(assign_var == 1)
        else:
            # Soft preference: multiple requesters, penalize non-assignment
            for e in requesters:
                assign_var = assignment_vars[(e, idx)]
                missed = model.NewBoolVar(f"missed_request_e{e}_s{idx}")
                model.Add(missed == 1 - assign_var)
                request_penalties.append(missed)

    return request_penalties