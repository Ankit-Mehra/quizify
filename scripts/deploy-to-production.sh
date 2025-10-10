#!/bin/bash
#
# deploy-to-production.sh
# 
# Deploys code from development branch to deploy/production branch
# Excludes tests, specs, and development documentation
# Only includes production-ready code and migrations
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 Production Deployment Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if there are uncommitted changes
if [[ -n $(git status -s) ]]; then
    echo -e "${YELLOW}⚠️  Warning: You have uncommitted changes${NC}"
    git status -s
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Deployment cancelled${NC}"
        exit 1
    fi
fi

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${BLUE}📍 Current branch: ${NC}$CURRENT_BRANCH"

# Ensure development branch is up to date
echo ""
echo -e "${BLUE}📥 Fetching latest changes...${NC}"
git fetch origin development
git fetch origin deploy/production

# Checkout development and ensure it's up to date
echo ""
echo -e "${BLUE}🔄 Updating development branch...${NC}"
git checkout development
git pull origin development

# Checkout production branch
echo ""
echo -e "${BLUE}🔄 Switching to deploy/production branch...${NC}"
git checkout deploy/production
git pull origin deploy/production

# Copy only production files from development
echo ""
echo -e "${BLUE}📦 Syncing production code from development...${NC}"

# Core application directories
echo "  ✓ Copying api/"
git checkout development -- api/ || true

echo "  ✓ Copying handlers/"
git checkout development -- handlers/ || true

echo "  ✓ Copying services/"
git checkout development -- services/ || true

echo "  ✓ Copying schemas/"
git checkout development -- schemas/ || true

echo "  ✓ Copying middleware/"
git checkout development -- middleware/ || true

echo "  ✓ Copying dependencies/"
git checkout development -- dependencies/ || true

# Core files
echo "  ✓ Copying core files (main.py, requirements.txt, etc.)"
git checkout development -- main.py || true
git checkout development -- requirements.txt || true
git checkout development -- pyproject.toml || true
git checkout development -- Dockerfile || true
git checkout development -- README.md || true

# Migrations (only .sql files)
echo "  ✓ Copying production migrations (*.sql)"
mkdir -p migrations
git checkout development -- migrations/*.sql 2>/dev/null || echo "    (no new migrations)"

# Check if there are any changes to commit
if [[ -z $(git status -s) ]]; then
    echo ""
    echo -e "${GREEN}✅ Production branch is already up to date!${NC}"
    echo ""
    git checkout $CURRENT_BRANCH
    exit 0
fi

# Show what changed
echo ""
echo -e "${BLUE}📝 Changes to be deployed:${NC}"
git status -s

# Confirm deployment
echo ""
read -p "$(echo -e ${YELLOW}Deploy these changes to production? ${NC})(y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${RED}❌ Deployment cancelled${NC}"
    echo -e "${BLUE}ℹ️  Resetting deploy/production branch...${NC}"
    git reset --hard origin/deploy/production
    git checkout $CURRENT_BRANCH
    exit 1
fi

# Create deployment commit
DEPLOY_DATE=$(date +%Y-%m-%d)
DEPLOY_TIME=$(date +%H:%M:%S)

echo ""
echo -e "${BLUE}💾 Creating deployment commit...${NC}"
git add api/ handlers/ services/ schemas/ middleware/ dependencies/ 2>/dev/null || true
git add main.py requirements.txt pyproject.toml Dockerfile README.md 2>/dev/null || true
git add migrations/*.sql 2>/dev/null || true

git commit -m "deploy: sync from development ($DEPLOY_DATE $DEPLOY_TIME)

Deployed by: $(git config user.name)
Source branch: development
Target branch: deploy/production

Changes:
$(git diff HEAD --stat)
"

# Push to remote
echo ""
echo -e "${BLUE}🚀 Pushing to origin/deploy/production...${NC}"
git push origin deploy/production

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 Deployment Summary:${NC}"
echo "  • Branch: deploy/production"
echo "  • Date: $DEPLOY_DATE"
echo "  • Time: $DEPLOY_TIME"
echo ""
echo -e "${BLUE}🔗 Next Steps:${NC}"
echo "  1. Check Railway dashboard for deployment status"
echo "  2. Monitor logs for any errors"
echo "  3. Test production endpoints"
echo ""

# Return to original branch
git checkout $CURRENT_BRANCH
echo -e "${BLUE}📍 Returned to branch: ${NC}$CURRENT_BRANCH"
echo ""
