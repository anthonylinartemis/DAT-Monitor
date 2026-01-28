#!/bin/bash
#
# DAT Monitor -> dbt-main Sync Script
#
# Exports holdings data to dbt seed files and optionally commits to dbt-main.
#
# Usage:
#   ./scripts/sync_to_dbt.sh              # Export and validate
#   ./scripts/sync_to_dbt.sh --commit     # Export, validate, and commit to dbt-main
#   ./scripts/sync_to_dbt.sh --dry-run    # Preview only, no file writes
#
# Requirements:
#   - SUPABASE_URL and SUPABASE_KEY environment variables
#   - Python 3.8+ with project dependencies
#   - dbt-main repo at ~/code/dbt-main/

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DBT_MAIN_PATH="${DBT_MAIN_PATH:-$HOME/code/dbt-main}"
DBT_SEEDS_PATH="$DBT_MAIN_PATH/seeds/digital_asset_treasury"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
COMMIT_CHANGES=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --commit)
            COMMIT_CHANGES=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--commit] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --commit    Commit changes to dbt-main repository"
            echo "  --dry-run   Preview export without writing files"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

echo "============================================================"
echo "DAT Monitor -> dbt-main Sync"
echo "============================================================"
echo "Project root: $PROJECT_ROOT"
echo "dbt-main path: $DBT_MAIN_PATH"
echo ""

# Check dbt-main exists
if [ ! -d "$DBT_MAIN_PATH" ]; then
    echo -e "${RED}ERROR: dbt-main not found at $DBT_MAIN_PATH${NC}"
    echo "Set DBT_MAIN_PATH environment variable to specify location."
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Step 1: Export to dbt seeds
echo "Step 1: Exporting holdings to dbt seeds..."
echo ""

EXPORT_ARGS="--all --output $DBT_SEEDS_PATH"
if [ "$DRY_RUN" = true ]; then
    EXPORT_ARGS="$EXPORT_ARGS --dry-run"
fi

if ! python scripts/export_dbt_seeds.py $EXPORT_ARGS; then
    echo -e "${RED}ERROR: Export failed${NC}"
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}Dry run complete - no files were written${NC}"
    exit 0
fi

# Step 2: Validate sync
echo ""
echo "Step 2: Validating sync..."
echo ""

if ! python scripts/validate_dbt_sync.py --seeds-path "$DBT_SEEDS_PATH"; then
    echo -e "${YELLOW}WARNING: Validation found issues (see above)${NC}"
    # Don't exit - we still want to commit if requested
fi

# Step 3: Commit to dbt-main (optional)
if [ "$COMMIT_CHANGES" = true ]; then
    echo ""
    echo "Step 3: Committing to dbt-main..."
    echo ""

    cd "$DBT_MAIN_PATH"

    # Check for changes
    if git diff --quiet "$DBT_SEEDS_PATH" && git diff --cached --quiet "$DBT_SEEDS_PATH"; then
        echo "No changes to commit."
    else
        # Show what changed
        echo "Changes detected:"
        git status --short "$DBT_SEEDS_PATH"
        echo ""

        # Stage changes
        git add "$DBT_SEEDS_PATH"

        # Create commit
        TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
        git commit -m "chore(dat): Auto-update DAT seeds from DAT Monitor

Updated: $TIMESTAMP
Source: DAT Monitor sync script"

        echo -e "${GREEN}Changes committed to dbt-main${NC}"
        echo ""
        echo "To push changes:"
        echo "  cd $DBT_MAIN_PATH && git push"
    fi

    cd "$PROJECT_ROOT"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}Sync complete!${NC}"
echo "============================================================"

if [ "$COMMIT_CHANGES" = false ]; then
    echo ""
    echo "Next steps:"
    echo "  1. Review changes in $DBT_SEEDS_PATH"
    echo "  2. Run: ./scripts/sync_to_dbt.sh --commit  # to commit"
    echo "  3. Or manually commit in dbt-main repo"
fi
