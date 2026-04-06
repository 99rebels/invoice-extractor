# Configuration Reference

Full details for `expense-config.json`, located in the skill root directory.

---

## Structure

The config file contains three top-level sections:

### categories

Keyword-to-category mappings for auto-categorization. The script checks `vendor` name and `description` against these keywords (case-insensitive).

```json
{
  "categories": {
    "software": ["github", "aws", "azure", "google cloud", "saas"],
    "travel": ["airline", "hotel", "uber", "lyft", "ryanair", "aer lingus"],
    "office": ["amazon", "staples", "ikea", "keyboard", "monitor"],
    "food": ["restaurant", "coffee", "tesco", "supermarket"]
  }
}
```

Users can add new categories or keywords by editing this file. Suggest additions when a vendor doesn't match any existing category.

### defaults

Default values used when fields are missing from extracted data:

```json
{
  "defaults": {
    "currency": "EUR",
    "taxRate": 0.23,
    "dateFormat": "YYYY-MM-DD"
  }
}
```

### ledger

CSV file path and backup settings:

```json
{
  "ledger": {
    "csvPath": "expenses.csv",
    "backupCount": 5
  }
}
```

---

## Custom Config

Use a custom config file with the `--config` flag:

```bash
python3 scripts/extract.py --config /path/to/config.json <command>
```

---

## View Current Categories

```bash
python3 scripts/extract.py categories
```
