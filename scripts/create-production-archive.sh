#!/bin/bash
# =============================================================================
# Quizify Production Deployment Script
# =============================================================================
# This script creates a clean production build using git archive, which
# automatically excludes files marked with 'export-ignore' in .gitattributes
#
# Usage:
#   ./scripts/create-production-archive.sh [branch_name]
#
# Example:
#   ./scripts/create-production-archive.sh development
#   ./scripts/create-production-archive.sh v1.2.3
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BRANCH="${1:-development}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="deploy-archives"
ARCHIVE_NAME="quizify-production-${BRANCH}-${TIMESTAMP}"
ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}.tar.gz"

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Quizify Production Archive Creator                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Check if branch exists
if ! git rev-parse --verify "${BRANCH}" >/dev/null 2>&1; then
    echo -e "${RED}✗ Error: Branch '${BRANCH}' does not exist${NC}"
    exit 1
fi

# Get commit hash
COMMIT_HASH=$(git rev-parse --short "${BRANCH}")

echo -e "${YELLOW}Configuration:${NC}"
echo -e "  Branch:       ${GREEN}${BRANCH}${NC}"
echo -e "  Commit:       ${GREEN}${COMMIT_HASH}${NC}"
echo -e "  Archive:      ${GREEN}${ARCHIVE_PATH}${NC}"
echo ""

# Create archive using git archive (respects .gitattributes export-ignore)
echo -e "${BLUE}📦 Creating production archive...${NC}"
git archive \
    --format=tar.gz \
    --prefix="${ARCHIVE_NAME}/" \
    --output="${ARCHIVE_PATH}" \
    "${BRANCH}"

# Get archive size
ARCHIVE_SIZE=$(du -h "${ARCHIVE_PATH}" | cut -f1)

echo -e "${GREEN}✓ Archive created successfully!${NC}"
echo -e "  Size:         ${GREEN}${ARCHIVE_SIZE}${NC}"
echo ""

# List what's included (first level)
echo -e "${BLUE}📋 Archive contents (top-level):${NC}"
tar -tzf "${ARCHIVE_PATH}" | sed 's|^[^/]*/||' | cut -d'/' -f1 | sort -u | head -20

echo ""
echo -e "${YELLOW}What's excluded (by .gitattributes):${NC}"
echo -e "  ✗ specs/          ${NC}(Specification documents)"
echo -e "  ✗ tests/          ${NC}(Test files)"
echo -e "  ✗ docs/           ${NC}(Development docs)"
echo -e "  ✗ scripts/        ${NC}(Development scripts)"
echo -e "  ✗ .github/        ${NC}(CI/CD workflows)"
echo -e "  ✗ htmlcov/        ${NC}(Coverage reports)"
echo -e "  ✗ __pycache__/    ${NC}(Python cache)"
echo ""

echo -e "${GREEN}✓ Production archive ready for deployment!${NC}"
echo -e "${BLUE}To deploy:${NC}"
echo -e "  1. scp ${ARCHIVE_PATH} user@server:/tmp/"
echo -e "  2. ssh user@server 'cd /app && tar -xzf /tmp/$(basename ${ARCHIVE_PATH}) --strip-components=1'"
echo -e "  3. ssh user@server 'cd /app && pip install -r requirements.txt'"
echo ""

# Optional: Verify critical files are present
echo -e "${BLUE}🔍 Verifying critical files...${NC}"
CRITICAL_FILES=(
    "main.py"
    "requirements.txt"
    "Dockerfile"
    "config.py"
    "api/"
    "handlers/"
    "services/"
    "schemas/"
    "dependencies/"
    "middleware/"
    "migrations/"
)

MISSING_FILES=()
for file in "${CRITICAL_FILES[@]}"; do
    if tar -tzf "${ARCHIVE_PATH}" | grep -q "${ARCHIVE_NAME}/${file}"; then
        echo -e "  ${GREEN}✓${NC} ${file}"
    else
        echo -e "  ${RED}✗${NC} ${file}"
        MISSING_FILES+=("${file}")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}⚠ Warning: Critical files missing from archive!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ All critical files present${NC}"
echo -e "${GREEN}✓ Production archive is ready!${NC}"
