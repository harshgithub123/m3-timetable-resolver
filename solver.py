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


def solve_timetable(data, time_limit_s=10.0):
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
    for i, sec in enumerate(sections):
        f_block = unavail.get(sec["faculty"], set())
        for d, p in all_slots:
            if (d, p) not in f_block:
                x[i, d, p] = model.NewBoolVar(f"x_{i}_{d}_{p}")

    for i, sec in enumerate(sections):
        vars_sec = [x[i, d, p] for d, p in all_slots if (i, d, p) in x]
        model.Add(sum(vars_sec) == sec["sessions"])
        for d in range(days):
            day_vars = [x[i, d, p] for p in range(periods) if (i, d, p) in x]
            if day_vars:
                model.Add(sum(day_vars) <= 1)

    fac_map = defaultdict(list)
    for i, sec in enumerate(sections):
        fac_map[sec["faculty"]].append(i)

    for fac, sec_idxs in fac_map.items():
        if len(sec_idxs) > 1:
            for d, p in all_slots:
                v = [x[i, d, p] for i in sec_idxs if (i, d, p) in x]
                if len(v) > 1:
                    model.Add(sum(v) <= 1)

    stu_map = defaultdict(list)
    for i, sec in enumerate(sections):
        for st in sec["enrolled"]:
            stu_map[st].append(i)

    unique_groups = {tuple(sorted(v)) for v in stu_map.values() if len(v) > 1}
    for grp in unique_groups:
        for d, p in all_slots:
            v = [x[i, d, p] for i in grp if (i, d, p) in x]
            if len(v) > 1:
                model.Add(sum(v) <= 1)

    cap_levels = sorted({r["capacity"] for r in rooms})
    for cap in cap_levels:
        rooms_ge = sum(1 for r in rooms if r["capacity"] >= cap)
        need_ge = [i for i, s in enumerate(sections) if len(s["enrolled"]) >= cap]
        if len(need_ge) > rooms_ge:
            for d, p in all_slots:
                v = [x[i, d, p] for i in need_ge if (i, d, p) in x]
                if len(v) > rooms_ge:
                    model.Add(sum(v) <= rooms_ge)

    for d, p in all_slots:
        v = [x[i, d, p] for i in range(len(sections)) if (i, d, p) in x]
        if len(v) > len(rooms):
            model.Add(sum(v) <= len(rooms))

    penalties = []
    for i in range(len(sections)):
        for d in range(days):
            if (i, d, lunch_p) in x:
                penalties.append(x[i, d, lunch_p] * 5)

    for fac, sec_idxs in fac_map.items():
        for d in range(days):
            for start_p in range(periods - max_consec):
                window = [
                    x[i, d, p]
                    for i in sec_idxs
                    for p in range(start_p, start_p + max_consec + 1)
                    if (i, d, p) in x
                ]
                if len(window) > max_consec:
                    over = model.NewBoolVar(f"consec_{fac}_{d}_{start_p}")
                    model.Add(sum(window) <= max_consec + over * len(window))
                    penalties.append(over * 2)

    if penalties:
        model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    elapsed = round(time.time() - t0, 2)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        schedule = []
        lunch_violations = 0
        for d, p in all_slots:
            active = [i for i in range(len(sections)) if (i, d, p) in x and solver.Value(x[i, d, p]) == 1]
            active.sort(key=lambda i: len(sections[i]["enrolled"]), reverse=True)
            avail_rooms = list(rooms)
            for i in active:
                sec = sections[i]
                size = len(sec["enrolled"])
                chosen_room = next((r for r in avail_rooms if r["capacity"] >= size), None)
                if chosen_room:
                    avail_rooms.remove(chosen_room)
                if p == lunch_p:
                    lunch_violations += 1
                schedule.append({
                    "day": d,
                    "period": p,
                    "section": sec["id"],
                    "course": sec["course"],
                    "faculty": sec["faculty"],
                    "room": chosen_room["id"] if chosen_room else "UNASSIGNED",
                    "enrolled_count": size
                })

        return {
            "feasible": True,
            "runtime_s": elapsed,
            "total_lectures": len(schedule),
            "lunch_violations": lunch_violations,
            "schedule": schedule
        }

    return {
        "feasible": False,
        "runtime_s": elapsed,
        "conflicting_sections": [],
        "conflicting_constraints": [{
            "type": "global_infeasible",
            "description": "No clash-free timetable exists under current hard constraints."
        }]
    }