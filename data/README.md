# Data Directory

This folder stores Excel files for import into Supabase.

## Files
- `DATs_Tracker_YYYY-MM-DD.xlsx` - Main DAT holdings tracker (not committed to git)

## Import Command
```bash
# Update the date to match your file
python scripts/import_excel.py --file ./data/DATs_Tracker_2026-01-19.xlsx --dry-run
```
