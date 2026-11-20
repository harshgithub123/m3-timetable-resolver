import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from solver import solve_timetable

app = FastAPI(title="M3 Timetable Clash Resolver")


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/solve")
async def solve_endpoint(file: UploadFile = File(...)):
    raw = await file.read()
    data = json.loads(raw.decode("utf-8"))
    return solve_timetable(data)