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

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

client = anthropic.Anthropic()

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv"}

IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

MAX_IMAGE_BYTES = 4_500_000
MAX_BATCH_BYTES = 10_000_000
MAX_FILES_PER_BATCH = 12
MAX_TEXT_CHARS = 8_000


def _ocr_image(path: Path) -> str | None:
    if not HAS_OCR:
        return None
    try:
        text = pytesseract.image_to_string(Image.open(path))
        return text.strip() or None
    except Exception:
        return None


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
                    text = text[:MAX_TEXT_CHARS * 4]  # PDFs can be large; generous limit
                    return {"type": "text", "content": text, "name": path.name, "bytes": len(text.encode())}
            raw = path.read_bytes()
            data = base64.standard_b64encode(raw).decode()
            return {"type": "pdf_b64", "content": data, "name": path.name, "bytes": len(raw)}

        if suffix in IMAGE_MEDIA:
            # Try free local OCR first
            ocr_text = _ocr_image(path)
            if ocr_text:
                return {"type": "text", "content": ocr_text[:MAX_TEXT_CHARS], "name": path.name, "bytes": len(ocr_text.encode()), "via_ocr": True}
            # Fall back to vision only if OCR yielded nothing
            raw = path.read_bytes()
            if len(raw) > MAX_IMAGE_BYTES:
                return {"type": "error", "name": path.name, "error": f"Image too large ({len(raw) // 1024} KB) and OCR unavailable"}
            data = base64.standard_b64encode(raw).decode()
            return {"type": "image", "content": data, "media_type": IMAGE_MEDIA[suffix], "name": path.name, "bytes": len(raw)}

        if suffix in {".txt", ".csv"}:
            text = path.read_text(errors="replace")[:MAX_TEXT_CHARS]
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
            label = f" [OCR]" if f.get("via_ocr") else ""
            blocks.append({"type": "text", "text": f"=== {f['name']}{label} ===\n{f['content']}\n"})
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
  "notes": ["any caveats or observations"]
}
Include every dollar amount you can find."""

SYNTHESIS_PROMPT = """You are an expert tax preparer. Combine these partial analyses from multiple document batches into one final report. Return ONLY a JSON object:
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

SYSTEM_PROMPT = "You are an expert tax preparer. Extract financial data from tax documents. Return ONLY raw JSON — no markdown, no code fences, no explanation."


def _call_claude(content_blocks: list[dict], model: str, use_thinking: bool, max_tokens: int = 4096) -> str:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    if use_thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    delay = 60
    for attempt in range(5):
        try:
            response = client.messages.create(**kwargs)
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
            time.sleep(62)
        names_in_batch = [f["name"] for f in batch]
        all_names.extend(names_in_batch)
        suffix = " (pausing 60s for rate limit)" if i > 0 else ""
        yield {
            "type": "analyzing",
            "message": f"Analyzing batch {i + 1} of {num_batches} ({len(batch)} files: {', '.join(names_in_batch[:3])}{'…' if len(names_in_batch) > 3 else ''}){suffix}…",
            "batch": i + 1,
            "total_batches": num_batches,
        }
        content_blocks = _build_content(batch)
        content_blocks.append({"type": "text", "text": BATCH_PROMPT})
        # Haiku for cheap batch extraction — no thinking needed for field extraction
        raw = _call_claude(content_blocks, model="claude-haiku-4-5-20251001", use_thinking=False)
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
        result["documents_analyzed"] = all_names
        result.setdefault("total_income", sum(x.get("amount", 0) for x in result.get("income", [])))
        result.setdefault("total_deductions", sum(x.get("amount", 0) for x in result.get("deductions", [])))
        result.setdefault("total_estimated_payments", sum(x.get("amount", 0) for x in result.get("estimated_payments", [])))
        result.setdefault("estimated_taxable_income", result.get("total_income", 0) - result.get("total_deductions", 0))
        result.setdefault("summary", "")
        result.setdefault("notes", [])
    else:
        yield {
            "type": "analyzing",
            "message": f"Synthesizing {num_batches} batches into final report…",
            "batch": num_batches + 1,
            "total_batches": num_batches + 1,
        }
        synthesis_input = json.dumps({"batches": batch_results}, indent=2)
        content_blocks = [
            {"type": "text", "text": f"Partial analyses from {num_batches} document batches:\n\n{synthesis_input}\n\n{SYNTHESIS_PROMPT}"}
        ]
        # Opus + thinking only for the synthesis step; 16k tokens to handle large document sets
        raw = _call_claude(content_blocks, model="claude-opus-4-7", use_thinking=True, max_tokens=16000)
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
