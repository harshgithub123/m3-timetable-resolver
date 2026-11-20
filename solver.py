import time
from collections import defaultdict
from ortools.sat.python import cp_model


def check_fast_conflicts(data):
    days = data["days"]
    periods = data["periods"]
    total_slots = days * periods
    rooms = data["rooms"]
    sections = data["sections"]
    unavail = data.get("faculty_unavailable", {})

    max_cap = max((r["capacity"] for r in rooms), default=0)

    # 1. Room capacity check
    for sec in sections:
        if len(sec["enrolled"]) > max_cap:
            return {
                "feasible": False,
                "conflicting_sections": [sec["id"]],
                "conflicting_constraints": [{
                    "type": "room_capacity",
                    "description": f"Section {sec['id']} has {len(sec['enrolled'])} students; largest room capacity is {max_cap}."
                }]
            }

    # 2. Faculty availability check
    fac_secs = defaultdict(list)
    for sec in sections:
        fac_secs[sec["faculty"]].append(sec)

    for fac, secs in fac_secs.items():
        needed = sum(s["sessions"] for s in secs)
        blocked = len(unavail.get(fac, []))
        available = total_slots - blocked
        if needed > available:
            sec_ids = [s["id"] for s in secs]
            return {
                "feasible": False,
                "conflicting_sections": sec_ids,
                "conflicting_constraints": [
                    {
                        "type": "faculty_availability",
                        "description": f"Faculty {fac} only has {available} available slot(s), but needs {needed} sessions."
                    },
                    {
                        "type": "faculty_double_booking",
                        "description": f"Faculty {fac} cannot teach two lectures at the same time (teaches: {', '.join(sec_ids)})."
                    }
                ]
            }

    # 3. Student overload check
    stu_secs = defaultdict(list)
    for sec in sections:
        for st in sec["enrolled"]:
            stu_secs[st].append(sec)

    for st, secs in stu_secs.items():
        needed = sum(s["sessions"] for s in secs)
        if needed > total_slots:
            sec_ids = [s["id"] for s in secs]
            return {
                "feasible": False,
                "conflicting_sections": sec_ids,
                "conflicting_constraints": [{
                    "type": "student_double_booking",
                    "description": f"Student {st} needs {needed} sessions across {len(sec_ids)} sections, but only {total_slots} slots exist."
                }]
            }

    return None


def solve_timetable(data, time_limit_s=50.0):
    t0 = time.time()

    fast_conflict = check_fast_conflicts(data)
    if fast_conflict:
        fast_conflict["runtime_s"] = round(time.time() - t0, 2)
        return fast_conflict

    days = data["days"]
    periods = data["periods"]
    lunch_p = data.get("lunch_period", 4)
    max_consec = data.get("max_consecutive", 3)
    rooms = sorted(data["rooms"], key=lambda r: r["capacity"])
    sections = data["sections"]
    unavail = {
        f: {(d, p) for d, p in slots}
        for f, slots in data.get("faculty_unavailable", {}).items()
    }

    model = cp_model.CpModel()
    all_slots = [(d, p) for d in range(days) for p in range(periods)]

    x = {}