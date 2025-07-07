"""
objective.py – weighted multi-criteria objective
"""

from ortools.sat.python import cp_model


def build_objective(model: cp_model.CpModel,
                    coverage_vars: dict,
                    spacing_vars: list,
                    overlap_vars,
                    multi_shift_penalties,
                    request_penalty_vars,
                    weights=None):
    """
    Tier-1: Minimize uncovered slots
    Tier-2: Minimize clustering (spacing)
    Requests are treated as HARD constraints: must be fulfilled.
    """
    if weights is None:
        weights = {
            "uncovered":   10_000,
            "spacing":       800,
            "overlap":       800,
            "multi_shift": 1_000,
        }

    # uncovered = 1 – covered
    uncovered_vars = []
    for s, cv in coverage_vars.items():
        u = model.NewBoolVar(f"uncovered_s{s}")
        model.Add(cv + u == 1)
        uncovered_vars.append(u)

    # All requests treated as hard
    for var in request_penalty_vars:
        model.Add(var == 1)

    model.Minimize(
          weights["uncovered"]   * sum(uncovered_vars)
        + weights["spacing"]     * sum(spacing_vars)
        + weights["overlap"]     * sum(overlap_vars)
        + weights["multi_shift"] * sum(multi_shift_penalties)
    )