# Invoice Extractor — Product Plan

## Product Overview

- **Name:** Invoice Extractor
- **One-liner:** Extract structured data from invoices and receipts — output JSON, CSV, or append to a running expense ledger
- **Target users:** Freelancers, small businesses, contractors who deal with invoices/receipts regularly
- **Pain point:** Manually typing invoice data into accounting software, or paying €15-30/month for tools like Dext/Hubdoc/Expensify

## ClawHub Competition

| Skill | Downloads | Focus | Gap |
|-------|-----------|-------|-----|
| finance-automation | 940 | Stripe webhooks + Telegram | Different product entirely |
| invoice-collector | 623 | Collects PDFs from Gmail | Doesn't extract data from them |
| receipt-expense-workbench | 198 | Normalizes receipts into ledger | No batch processing, limited extraction |
| receipt-expense-reconciler | 100 | Parses receipts, categorizes, tax summaries | Smaller scope, no configurable categories |

**Our gap:** None focus on high-quality structured extraction with batch processing and configurable categories. We sit between "collect" and "reconcile" — the actual extraction step.

## v1.0.0 MVP Scope

- Single PDF extraction (text-based PDFs via pdfplumber)
- Single image extraction (via LLM vision — agent handles this, not the script)
- Batch folder processing
- JSON output (per invoice)
- CSV output (batch or ledger)
- Configurable expense categories with keyword matching
- Running expense ledger (append mode)
- Filter/view ledger by date range, category, vendor
- Zero external APIs required (LLM does extraction for images, pdfplumber for PDFs)

## v1.0.0 Non-Scope

- Email integration (separate skill's job)
- Accounting software API uploads (Xero, FreeAgent, Wave)
- Multi-currency conversion
- Receipt photo capture from phone
- OCR for scanned PDFs (use LLM vision as fallback)
- Duplicate detection

## Technical Architecture

- **Language:** Python 3.13
- **Script:** `scripts/extract.py` — single entry point
- **Dependencies:** pdfplumber (pip), stdlib for everything else
- **Config:** `expense-config.json` in skill directory or user-configurable path
- **Data:** `data/ledger.csv` (user's accumulated expenses)
- **Commands:** extract, batch, ledger, categories

### Design Philosophy

The script is a **tool**, not a brain. It handles:
- PDF text extraction (pdfplumber)
- CSV ledger management (CRUD, backups, queries)
- Batch file discovery
- Config loading

The **agent (LLM)** handles the actual parsing/extraction because it's far better at understanding varied invoice formats than regex. This hybrid approach gives us:
- Robust text extraction from PDFs
- Intelligent parsing of any invoice format
- Vision support for image receipts
- No external API dependencies

## Commands

### `--pdf <file>`
Extract raw text from a PDF. The agent then parses this text into structured data.

### `batch <folder>`
Recursively list all PDFs and images in a folder as JSON. The agent processes each one.

### `ledger --add <json-file-or-stdin>`
Append a structured expense entry to the CSV ledger. Auto-categorizes based on config keywords.

### `ledger --view [--from DATE] [--to DATE] [--category CAT] [--vendor VENDOR] [--format csv|json]`
Query the ledger with filters.

### `ledger --summary [--period week|month|year]`
Aggregate totals by category.

### `categories`
List current categories from config.

## Config (expense-config.json)

```json
{
  "categories": {
    "software": ["github", "aws", "google cloud", "vercel", "openai", "anthropic", "azure"],
    "travel": ["ryanair", "airbnb", "hotel", "taxi", "uber", "bus éireann", "irish rail"],
    "office": ["staples", "amazon", "equipment", "monitor", "keyboard"],
    "utilities": ["electric", "gas", "internet", "phone", "vodafone", "virgin", "eir"],
    "food": ["restaurant", "cafe", "tesco", "supervalu", "lidl", "aldi", "insomnia", "starbucks"],
    "professional": ["accountant", "legal", "insurance", "subscription", "membership"]
  },
  "defaults": {
    "currency": "EUR",
    "taxRate": 0.23,
    "dateFormat": "%Y-%m-%d"
  },
  "ledger": {
    "path": "data/ledger.csv",
    "backupCount": 5
  }
}
```

## CSV Ledger Format

```csv
id,date,vendor,description,category,subtotal,tax,total,currency,source_file,extracted_at
1,2026-04-01,Amazon,Office supplies,office,45.00,9.22,54.22,EUR,receipt_amazon_20260401.pdf,2026-04-01T10:30:00Z
```

## File Structure

```
invoice-extractor/
├── SKILL.md
├── references/
│   └── product-plan.md
├── scripts/
│   └── extract.py
├── data/
│   └── .gitkeep
└── expense-config.json
```

## Roadmap

- **v1.1:** Duplicate detection (hash-based)
- **v1.2:** Multi-currency support
- **v1.3:** Export to Xero/FreeAgent format
- **v2.0:** Email integration (auto-process invoice attachments)
