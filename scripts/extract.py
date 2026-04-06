#!/usr/bin/env python3
"""
Invoice Extractor — PDF text extraction, batch file discovery, and CSV ledger management.

Usage:
    python3 extract.py --pdf <file>
    python3 extract.py batch <folder>
    python3 extract.py ledger --add <json-file-or->
    python3 extract.py ledger --view [--from DATE] [--to DATE] [--category CAT] [--vendor VENDOR] [--format json|csv]
    python3 extract.py ledger --summary [--period week|month|year]
    python3 extract.py categories
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "categories": {
        "software": ["github", "aws", "google cloud", "vercel", "openai", "anthropic", "azure"],
        "travel": ["ryanair", "airbnb", "hotel", "taxi", "uber", "bus éireann", "irish rail"],
        "office": ["staples", "amazon", "equipment", "monitor", "keyboard"],
        "utilities": ["electric", "gas", "internet", "phone", "vodafone", "virgin", "eir"],
        "food": ["restaurant", "cafe", "tesco", "supervalu", "lidl", "aldi", "insomnia", "starbucks"],
        "professional": ["accountant", "legal", "insurance", "subscription", "membership"],
    },
    "defaults": {
        "currency": "EUR",
        "taxRate": 0.23,
        "dateFormat": "%Y-%m-%d",
    },
    "ledger": {
        "path": "data/ledger.csv",
        "backupCount": 5,
    },
}

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def load_config(config_path: str | None = None) -> dict:
    """Load config from file, falling back through search paths then defaults."""
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.extend([
        SCRIPT_DIR / "expense-config.json",
        SKILL_DIR / "expense-config.json",
    ])
    for p in candidates:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: failed to load config {p}: {e}", file=sys.stderr)
                break
    return DEFAULT_CONFIG


def resolve_ledger_path(config: dict) -> Path:
    """Resolve the ledger CSV path relative to the skill directory."""
    raw = config.get("ledger", {}).get("path", "data/ledger.csv")
    p = Path(raw)
    if not p.is_absolute():
        p = SKILL_DIR / p
    return p


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(filepath: str) -> str:
    """Extract text from a PDF file. Returns text string or raises."""
    # Try pdfplumber first
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text()
                if t:
                    texts.append(t)
        if texts:
            return "\n".join(texts)
        print("Warning: pdfplumber extracted no text (possibly a scanned PDF)", file=sys.stderr)
        print("Consider extracting the first page as an image and using the agent's vision tool.", file=sys.stderr)
        return ""
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: pdfplumber failed: {e}", file=sys.stderr)

    # Fallback: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise RuntimeError("PDF is encrypted and requires a password.")
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        if texts:
            return "\n".join(texts)
        return ""
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: PyPDF2 failed: {e}", file=sys.stderr)

    print("Error: no PDF library available. Install one with:", file=sys.stderr)
    print("  pip install pdfplumber", file=sys.stderr)
    print("  # or: pip install PyPDF2", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Batch file discovery
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
PDF_EXTENSIONS = {".pdf"}


def batch_scan(folder: str) -> list[dict]:
    """Recursively find all PDF and image files in a folder."""
    root = Path(folder)
    if not root.is_dir():
        print(f"Error: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in PDF_EXTENSIONS:
            ftype = "pdf"
        elif ext in IMAGE_EXTENSIONS:
            ftype = "image"
        else:
            continue
        stat = p.stat()
        files.append({
            "path": str(p.resolve()),
            "name": p.name,
            "size": stat.st_size,
            "type": ftype,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    # Sort newest first
    files.sort(key=lambda x: x["modified"], reverse=True)
    return files


# ---------------------------------------------------------------------------
# Ledger management
# ---------------------------------------------------------------------------

LEDGER_HEADERS = [
    "id", "date", "vendor", "description", "category",
    "subtotal", "tax", "total", "currency", "source_file", "extracted_at",
]


def auto_categorize(vendor: str, description: str, config: dict) -> str:
    """Match vendor/description against category keywords."""
    search_text = f"{vendor} {description}".lower()
    categories = config.get("categories", {})
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw.lower() in search_text:
                return cat
    return "uncategorized"


def backup_ledger(ledger_path: Path, backup_count: int):
    """Create a rotated backup of the ledger file."""
    if not ledger_path.exists():
        return
    for i in range(backup_count, 0, -1):
        src = ledger_path if i == 1 else ledger_path.with_suffix(f".csv.bak.{i-1}")
        dst = ledger_path.with_suffix(f".csv.bak.{i}")
        if src.exists():
            shutil.copy2(src, dst)


def next_id(ledger_path: Path) -> int:
    """Get the next sequential ID for the ledger."""
    if not ledger_path.exists():
        return 1
    try:
        with open(ledger_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return 1
            return max((int(r["id"]) for r in rows if r.get("id", "").isdigit()), default=0) + 1
    except Exception:
        return 1


def read_ledger(ledger_path: Path) -> list[dict]:
    """Read the full ledger CSV into a list of dicts."""
    if not ledger_path.exists():
        return []
    try:
        with open(ledger_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Error reading ledger: {e}", file=sys.stderr)
        return []


def write_ledger_entry(ledger_path: Path, entry: dict, config: dict):
    """Append an entry to the ledger CSV."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    backup_count = config.get("ledger", {}).get("backupCount", 5)
    backup_ledger(ledger_path, backup_count)

    file_exists = ledger_path.exists()
    with open(ledger_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_HEADERS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


def ledger_add(json_input: str | None, config: dict, source_file: str | None = None):
    """Add an entry to the ledger from JSON input."""
    # Read JSON
    try:
        if json_input and json_input != "-":
            with open(json_input, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)
    except Exception as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate required fields
    for field in ("vendor", "total", "date"):
        if field not in data or not data[field]:
            print(f"Error: missing required field '{field}'", file=sys.stderr)
            sys.exit(1)

    ledger_path = resolve_ledger_path(config)

    # Normalize date
    date_fmt = config.get("defaults", {}).get("dateFormat", "%Y-%m-%d")
    date_val = str(data["date"])
    # Try to parse common formats and normalize to YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            date_val = datetime.strptime(date_val, fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            continue

    # Auto-categorize if not specified
    category = data.get("category") or auto_categorize(
        data["vendor"], data.get("description", ""), config
    )

    entry = {
        "id": next_id(ledger_path),
        "date": date_val,
        "vendor": str(data["vendor"]).strip(),
        "description": str(data.get("description", "")).strip(),
        "category": category,
        "subtotal": str(data.get("subtotal", "")),
        "tax": str(data.get("tax", "")),
        "total": str(data["total"]),
        "currency": str(data.get("currency", config.get("defaults", {}).get("currency", "EUR"))),
        "source_file": str(source_file or data.get("source_file", "")),
        "extracted_at": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    write_ledger_entry(ledger_path, entry, config)
    print(json.dumps(entry, indent=2))


def parse_date_filter(date_str: str) -> datetime | None:
    """Parse a date filter string into a datetime."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def ledger_view(config: dict, from_date: str = None, to_date: str = None,
                category: str = None, vendor: str = None, fmt: str = "json"):
    """View ledger entries with optional filters."""
    ledger_path = resolve_ledger_path(config)
    rows = read_ledger(ledger_path)

    if not rows:
        print("No entries in ledger." if fmt == "json" else "No entries in ledger.")
        return

    from_dt = parse_date_filter(from_date)
    to_dt = parse_date_filter(to_date)

    filtered = []
    for row in rows:
        # Date filter
        if from_dt or to_dt:
            row_date = parse_date_filter(row.get("date", ""))
            if row_date:
                if from_dt and row_date < from_dt:
                    continue
                if to_dt and row_date > to_dt + timedelta(days=1) - timedelta(seconds=1):
                    continue
        # Category filter
        if category and row.get("category", "").lower() != category.lower():
            continue
        # Vendor filter (partial match)
        if vendor and vendor.lower() not in row.get("vendor", "").lower():
            continue
        filtered.append(row)

    if fmt == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=LEDGER_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in filtered:
            writer.writerow(row)
    else:
        total = sum(float(r.get("total", 0) or 0) for r in filtered)
        output = {"entries": filtered, "count": len(filtered), "total": round(total, 2)}
        print(json.dumps(output, indent=2))


def ledger_summary(config: dict, period: str = None):
    """Summarize ledger by category."""
    ledger_path = resolve_ledger_path(config)
    rows = read_ledger(ledger_path)

    if not rows:
        print("No entries in ledger.")
        return

    now = datetime.now()
    if period == "week":
        from_dt = now - timedelta(days=7)
    elif period == "month":
        from_dt = now.replace(day=1)
    elif period == "year":
        from_dt = now.replace(month=1, day=1)
    else:
        from_dt = None

    categories: dict[str, float] = {}
    count = 0
    for row in rows:
        if from_dt:
            row_date = parse_date_filter(row.get("date", ""))
            if row_date and row_date < from_dt:
                continue
        cat = row.get("category", "uncategorized")
        total = float(row.get("total", 0) or 0)
        categories[cat] = categories.get(cat, 0) + total
        count += 1

    grand_total = round(sum(categories.values()), 2)
    output = {
        "period": period or "all",
        "entryCount": count,
        "categories": {k: round(v, 2) for k, v in sorted(categories.items(), key=lambda x: -x[1])},
        "grandTotal": grand_total,
    }
    print(json.dumps(output, indent=2))


def list_categories(config: dict):
    """List all configured categories and their keywords."""
    categories = config.get("categories", {})
    print(json.dumps(categories, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Invoice Extractor — extract text from PDFs, manage expense ledger",
    )
    parser.add_argument("--config", "-c", help="Path to config JSON file")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --pdf
    pdf_parser = subparsers.add_parser("pdf", help="Extract text from a PDF file")
    pdf_parser.add_argument("file", help="Path to PDF file")

    # batch
    batch_parser = subparsers.add_parser("batch", help="List PDFs and images in a folder")
    batch_parser.add_argument("folder", help="Path to folder")

    # ledger
    ledger_parser = subparsers.add_parser("ledger", help="Manage expense ledger")
    ledger_sub = ledger_parser.add_subparsers(dest="ledger_command")

    # ledger --add
    add_parser = ledger_sub.add_parser("add", help="Add entry to ledger")
    add_parser.add_argument("json_file", nargs="?", help="JSON file path (or - for stdin)")
    add_parser.add_argument("--source", help="Source filename for the entry")

    # ledger --view
    view_parser = ledger_sub.add_parser("view", help="View ledger entries")
    view_parser.add_argument("--from", dest="from_date", help="Filter from date (YYYY-MM-DD)")
    view_parser.add_argument("--to", dest="to_date", help="Filter to date (YYYY-MM-DD)")
    view_parser.add_argument("--category", help="Filter by category")
    view_parser.add_argument("--vendor", help="Filter by vendor (partial match)")
    view_parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    # ledger --summary
    summary_parser = ledger_sub.add_parser("summary", help="Summarize expenses by category")
    summary_parser.add_argument("--period", choices=["week", "month", "year"], help="Time period")

    # categories
    subparsers.add_parser("categories", help="List configured expense categories")

    args = parser.parse_args()
    config = load_config(args.config if hasattr(args, "config") else None)

    if args.command == "pdf":
        text = extract_pdf_text(args.file)
        if text:
            print(text)
    elif args.command == "batch":
        files = batch_scan(args.folder)
        print(json.dumps(files, indent=2))
    elif args.command == "ledger":
        if args.ledger_command == "add":
            ledger_add(args.json_file, config, args.source)
        elif args.ledger_command == "view":
            ledger_view(config, args.from_date, args.to_date, args.category, args.vendor, args.format)
        elif args.ledger_command == "summary":
            ledger_summary(config, args.period)
        else:
            ledger_parser.print_help()
    elif args.command == "categories":
        list_categories(config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
