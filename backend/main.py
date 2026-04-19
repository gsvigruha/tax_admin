import json
import os
import subprocess
from pathlib import Path

# LLMObs must be enabled before the Anthropic client is instantiated (imported from analyzer)
_dd_api_key = os.environ.get("DD_API_KEY")
if _dd_api_key:
    from ddtrace.llmobs import LLMObs
    LLMObs.enable(
        ml_app="tax_admin",
        agentless_enabled=True,
        api_key=_dd_api_key,
        site=os.environ.get("DD_SITE", "datadoghq.com"),
    )

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from analyzer import analyze_stream, SUPPORTED

app = FastAPI(title="AI Tax Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS_FILE = Path("tax_results.json")


@app.exception_handler(anthropic.APIError)
async def anthropic_error_handler(_: Request, exc: anthropic.APIError):
    return JSONResponse(status_code=502, content={"detail": f"Anthropic API error: {exc.message}"})


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


class FolderRequest(BaseModel):
    folder_path: str


@app.get("/api/pick-folder")
def pick_folder():
    result = subprocess.run(
        ["osascript", "-e", "POSIX path of (choose folder)"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail="No folder selected")
    return {"path": result.stdout.strip()}


@app.get("/")
def root():
    return {"message": "AI Tax Assistant API — open http://localhost:5173 for the UI"}


@app.post("/api/scan")
def scan_folder(req: FolderRequest):
    folder = Path(req.folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")
    files = [
        {"name": f.name, "path": str(f), "type": f.suffix.lower()}
        for f in sorted(folder.rglob("*"))
        if f.is_file() and f.suffix.lower() in SUPPORTED
    ]
    return {"files": files, "total": len(files)}


@app.post("/api/analyze-stream")
def analyze_stream_endpoint(req: FolderRequest):
    folder = Path(req.folder_path).expanduser()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")

    def event_stream():
        try:
            for event in analyze_stream(folder):
                if event.get("type") == "done":
                    RESULTS_FILE.write_text(json.dumps(event["result"], indent=2))
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/results")
def get_results():
    if not RESULTS_FILE.exists():
        return {"exists": False, "data": None}
    return {"exists": True, "data": json.loads(RESULTS_FILE.read_text())}
