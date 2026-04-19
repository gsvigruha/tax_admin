import base64
import json
import re
import time
from pathlib import Path
from typing import Generator

import anthropic

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

client = anthropic.Anthropic()

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv"}

IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# 4.5 MB decoded bytes — stays under the 5 MB API limit per image
MAX_IMAGE_BYTES = 4_500_000
# ~10 MB total decoded payload per batch
MAX_BATCH_BYTES = 10_000_000
MAX_FILES_PER_BATCH = 12


def read_file(path: Path) -> dict | None:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        return None
    try:
        if suffix == ".pdf":
            if HAS_PDFPLUMBER:
                with pdfplumber.open(path) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                if text.strip():
                    return {"type": "text", "content": text, "name": path.name, "bytes": len(text.encode())}
            raw = path.read_bytes()
            data = base64.standard_b64encode(raw).decode()
            return {"type": "pdf_b64", "content": data, "name": path.name, "bytes": len(raw)}
        if suffix in IMAGE_MEDIA:
            raw = path.read_bytes()
            if len(raw) > MAX_IMAGE_BYTES:
                return {"type": "error", "name": path.name, "error": f"Image too large ({len(raw) // 1024} KB > {MAX_IMAGE_BYTES // 1024} KB limit)"}
            data = base64.standard_b64encode(raw).decode()
            return {"type": "image", "content": data, "media_type": IMAGE_MEDIA[suffix], "name": path.name, "bytes": len(raw)}
        if suffix in {".txt", ".csv"}:
            text = path.read_text(errors="replace")
            return {"type": "text", "content": text, "name": path.name, "bytes": len(text.encode())}
    except Exception as exc:
        return {"type": "error", "name": path.name, "error": str(exc)}
    return None


def _make_batches(file_data: list[dict]) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_bytes = 0

    for f in file_data:
        size = f.get("bytes", 0)
        if current and (current_bytes + size > MAX_BATCH_BYTES or len(current) >= MAX_FILES_PER_BATCH):
            batches.append(current)
            current = [f]
            current_bytes = size
        else:
            current.append(f)
            current_bytes += size

    if current:
        batches.append(current)

    return batches


def _build_content(files: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for f in files:
        if f["type"] == "text":
            blocks.append({"type": "text", "text": f"=== {f['name']} ===\n{f['content']}\n"})
        elif f["type"] == "pdf_b64":
            blocks.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": f["content"]},
                "title": f["name"],
            })
        elif f["type"] == "image":
            blocks.append({"type": "text", "text": f"=== {f['name']} ==="})
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": f["media_type"], "data": f["content"]},
            })
    return blocks


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


BATCH_PROMPT = """Analyze the tax documents above and extract all financial data. Return ONLY a JSON object:
{
  "documents_analyzed": ["filename1"],
  "income": [{"description": "...", "amount": 0.00, "source": "...", "type": "W2|1099-NEC|1099-MISC|1099-INT|1099-DIV|other"}],
  "deductions": [{"description": "...", "amount": 0.00, "category": "business|medical|charitable|mortgage|state_tax|other"}],
  "estimated_payments": [{"description": "...", "amount": 0.00, "date": "...", "jurisdiction": "federal|state|NYC|other"}],
  "notes": ["any caveats, missing info, or observations"]
}
Include every dollar amount you can find. Use 0.00 for unknown amounts."""

SYNTHESIS_PROMPT = """You are an expert tax preparer. You have received partial analyses from multiple batches of tax documents. Combine them into one comprehensive final analysis. Return ONLY a JSON object:
{
  "documents_analyzed": ["all filenames"],
  "income": [{"description": "...", "amount": 0.00, "source": "...", "type": "W2|1099-NEC|1099-MISC|1099-INT|1099-DIV|other"}],
  "deductions": [{"description": "...", "amount": 0.00, "category": "business|medical|charitable|mortgage|state_tax|other"}],
  "estimated_payments": [{"description": "...", "amount": 0.00, "date": "...", "jurisdiction": "federal|state|NYC|other"}],
  "total_income": 0.00,
  "total_deductions": 0.00,
  "total_estimated_payments": 0.00,
  "estimated_taxable_income": 0.00,
  "summary": "One paragraph plain-English summary of the full tax picture",
  "notes": ["caveats or missing info"]
}
Deduplicate entries that appear in multiple batches. Compute all totals accurately."""

SYSTEM_PROMPT = "You are an expert tax preparer. Analyze tax documents and extract financial data. Return ONLY raw JSON with no markdown formatting, no code fences, no explanation."


def _call_claude(content_blocks: list[dict]) -> str:
    delay = 60
    for attempt in range(5):
        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content_blocks}],
            )
            return next((b.text for b in response.content if b.type == "text"), "{}")
        except anthropic.RateLimitError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 300)


def analyze_stream(folder: Path) -> Generator[dict, None, None]:
    candidates = [f for f in sorted(folder.rglob("*")) if f.is_file() and f.suffix.lower() in SUPPORTED]

    if not candidates:
        yield {"type": "done", "result": {
            "documents_analyzed": [], "income": [], "deductions": [], "estimated_payments": [],
            "total_income": 0, "total_deductions": 0, "total_estimated_payments": 0,
            "estimated_taxable_income": 0, "summary": "No supported documents found.", "notes": [],
        }}
        return

    total = len(candidates)
    file_data = []
    skipped = []

    for i, f in enumerate(candidates):
        yield {"type": "file", "name": f.name, "current": i + 1, "total": total}
        result = read_file(f)
        if result and result["type"] != "error":
            file_data.append(result)
        elif result and result["type"] == "error":
            skipped.append(f"{f.name}: {result['error']}")

    batches = _make_batches(file_data)
    num_batches = len(batches)

    batch_results = []
    all_names = []

    for i, batch in enumerate(batches):
        if i > 0:
            time.sleep(62)  # stay under 30k tokens/min rate limit
        names_in_batch = [f["name"] for f in batch]
        all_names.extend(names_in_batch)
        suffix = f" (waiting 60s between batches to avoid rate limits)" if i > 0 else ""
        yield {
            "type": "analyzing",
            "message": f"Analyzing batch {i + 1} of {num_batches} ({len(batch)} files: {', '.join(names_in_batch[:3])}{'…' if len(names_in_batch) > 3 else ''}){suffix}…",
            "batch": i + 1,
            "total_batches": num_batches,
        }
        content_blocks = _build_content(batch)
        content_blocks.append({"type": "text", "text": BATCH_PROMPT})
        raw = _call_claude(content_blocks)
        parsed = _extract_json(raw)
        if parsed:
            parsed.setdefault("documents_analyzed", names_in_batch)
            batch_results.append(parsed)
        else:
            batch_results.append({
                "documents_analyzed": names_in_batch,
                "income": [], "deductions": [], "estimated_payments": [],
                "notes": [f"Could not parse batch {i + 1} response: {raw[:500]}"],
            })

    if num_batches == 1:
        result = batch_results[0]
        result.setdefault("documents_analyzed", all_names)
        result.setdefault("total_income", sum(x.get("amount", 0) for x in result.get("income", [])))
        result.setdefault("total_deductions", sum(x.get("amount", 0) for x in result.get("deductions", [])))
        result.setdefault("total_estimated_payments", sum(x.get("amount", 0) for x in result.get("estimated_payments", [])))
        result.setdefault("estimated_taxable_income", result.get("total_income", 0) - result.get("total_deductions", 0))
        result.setdefault("summary", "")
        result.setdefault("notes", [])
    else:
        yield {"type": "analyzing", "message": f"Synthesizing {num_batches} batch results into final report…", "batch": num_batches + 1, "total_batches": num_batches + 1}
        synthesis_input = json.dumps({"batches": batch_results}, indent=2)
        content_blocks = [
            {"type": "text", "text": f"Here are the partial analyses from {num_batches} batches of tax documents:\n\n{synthesis_input}\n\n{SYNTHESIS_PROMPT}"}
        ]
        raw = _call_claude(content_blocks)
        result = _extract_json(raw) or {
            "documents_analyzed": all_names,
            "income": [], "deductions": [], "estimated_payments": [],
            "total_income": 0, "total_deductions": 0, "total_estimated_payments": 0,
            "estimated_taxable_income": 0,
            "summary": raw[:2000],
            "notes": ["Could not parse synthesis response."],
        }

    if skipped:
        result.setdefault("notes", [])
        result["notes"].extend([f"Skipped: {s}" for s in skipped])

    result["documents_analyzed"] = all_names
    yield {"type": "done", "result": result}
