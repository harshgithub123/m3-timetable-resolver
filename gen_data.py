import argparse, json, random

ap = argparse.ArgumentParser()
ap.add_argument("--students", type=int, default=1500)
ap.add_argument("--sections", type=int, default=120)
ap.add_argument("--rooms", type=int, default=30)
ap.add_argument("--sessions", type=int, default=3)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--infeasible", choices=["none", "faculty", "student", "capacity"], default="none")
ap.add_argument("--out", default="big.json")
a = ap.parse_args()
rng = random.Random(a.seed)

n_elec = max(4, a.sections // 6)
n_core = a.sections - n_elec
batches = max(1, n_core // 4)
per_batch = a.students // batches
sections = []
for i in range(a.sections):
    sections.append({
        "id": ("CORE-%03d" % i) if i < n_core else ("ELEC-%03d" % i),
        "course": "C%03d" % (i // 2),
        "faculty": "F%03d" % (i % max(10, a.sections // 2)),
        "sessions": a.sessions,
        "enrolled": []
    })

sid = 0
for b in range(batches):
    mine = list(range(b * 4, b * 4 + 4))
    for _ in range(per_batch):
        sid += 1
        st = "S%04d" % sid
        for i in mine:
            sections[i]["enrolled"].append(st)
        sections[n_core + rng.randrange(n_elec)]["enrolled"].append(st)
        if rng.random() < 0.08:
            j = rng.randrange(n_core)
            if j not in mine:
                sections[j]["enrolled"].append(st)

caps = [40, 60, 60, 80, 80, 100, 120]
rooms = [{"id": "R%03d" % (i + 1), "capacity": caps[i % len(caps)]} for i in range(a.rooms)]
data = {
    "days": 5, "periods": 8, "lunch_period": 4, "max_consecutive": 3,
    "rooms": rooms, "sections": sections, "faculty_unavailable": {}
}

if a.infeasible == "faculty":
    free = {(0, 1), (1, 2), (2, 3), (3, 1), (4, 2)}
    data["faculty_unavailable"]["F000"] = [[d, p] for d in range(5) for p in range(8) if (d, p) not in free]
elif a.infeasible == "student":
    for s in sections[:14]:
        s["enrolled"].append("S_OVERLOAD")
elif a.infeasible == "capacity":
    sections[5]["enrolled"] += ["X%03d" % i for i in range(150)]

json.dump(data, open(a.out, "w"))
print("wrote", a.out)