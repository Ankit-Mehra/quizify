# Archived Specification Files

**Archive Date**: 2025-10-28  
**Reason**: Superseded by IMPLEMENTED_* contract files

---

## Files in This Archive

### 1. `generate-quiz-from-url.md`
**Original Purpose**: Specification for URL-based quiz generation  
**Superseded By**: `IMPLEMENTED_generate-quiz-from-url.md`  
**Status**: ✅ Fully implemented in current codebase

### 2. `generate-quiz-quota.md`
**Original Purpose**: Specification for quota validation in quiz generation  
**Superseded By**: All `IMPLEMENTED_generate-*` files now document quota enforcement  
**Status**: ✅ Quota validation implemented in all generation endpoints

### 3. `file-upload-validation.md`
**Original Purpose**: Specification for file upload validation and tier restrictions  
**Superseded By**: `IMPLEMENTED_file-endpoints.md`  
**Status**: ✅ File upload implemented (10MB limit, PDF/DOCX support)

---

## Why These Were Archived

These files represented the **original specifications** (what we planned to build) but have now been superseded by **implementation contracts** (what we actually built).

### Key Differences: Spec vs Implementation

**Original Specs Said:**
- Tier-based file type restrictions (free=PDF+TXT, basic=+DOCX, educator=all)
- Complex quota validation logic
- Specific error codes and messages

**What Was Actually Implemented:**
- Simpler validation (all tiers: PDF+DOCX, 10MB limit)
- Quota validation before generation (all endpoints)
- Standardized error responses

---

## Historical Value

These files remain useful for:
- Understanding original design intent
- Comparing spec vs implementation choices
- Historical context for future refactoring
- Learning from design evolution

---

## Current Documentation

For current API behavior, see the parent `contracts/` folder:
- `CONTRACTS_INDEX.md` - Complete index of all endpoints
- `IMPLEMENTED_*.md` - Actual implementation contracts
- `README_ACTUAL_vs_SPEC.md` - Folder structure guide
