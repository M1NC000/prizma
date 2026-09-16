from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from engine.compute import generate_tickets  # noqa: E402

app = FastAPI(title="Prizma", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/styles.css")
def css():
    return FileResponse(WEB / "styles.css")


@app.get("/app.js")
def js():
    return FileResponse(WEB / "app.js")


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    return FileResponse(WEB / "favicon.svg")


@app.get("/learn.css")
def learn_css():
    return FileResponse(WEB / "learn.css")


@app.get("/learn.js")
def learn_js():
    return FileResponse(WEB / "learn.js")


@app.get("/health")
@app.get("/api/health")
def health():
    return {"ok": True, "name": "Prizma"}


@app.get("/api/learning")
def learning():
    path = WEB / "assets" / "learning.json"
    if not path.exists():
        return {"ok": False, "error": "learning.json ešte nie je vypočítaný"}
    return FileResponse(path)


@app.get("/api/tickets")
def tickets(
    strategy: str = Query("lab"),
    era: str = Query("current"),
    n: int = Query(8, ge=1, le=30),
    seed: int = Query(1),
):
    allowed = {"random", "hot", "cold", "overdue", "balanced", "lab"}
    if strategy not in allowed:
        strategy = "lab"
    if era not in {"current", "2of12_tue_fri", "2of10_friday", "2of8_friday", "all"}:
        era = "current"
    return generate_tickets(era, strategy, n, seed)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
