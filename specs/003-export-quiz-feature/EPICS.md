# Export Quiz Feature - Epic Breakdown

**Feature**: Robust Quiz Export System  
**Version**: 1.0.0  
**Created**: 2025-11-25  
**Status**: Planning

---

## Executive Summary

Implement a comprehensive quiz export system supporting multiple formats for different use cases:
- **Ship Quickly Formats**: PDF, DOCX, CSV (native), CSV (Anki), Share Link
- **LMS-Ready Formats**: QTI 2.1 (XML), Moodle XML

---

## Tier-Based Feature Access

| Feature | Free | Basic | Pro |
|---------|------|-------|-----|
| PDF Export | ✅ | ✅ | ✅ |
| DOCX Export | ✅ | ✅ | ✅ |
| CSV (Quizify Native) | ✅ | ✅ | ✅ |
| CSV (Anki) | ✅ | ✅ | ✅ |
| Share Link | ✅ | ✅ | ✅ |
| **QTI 2.1 Export (LMS)** | ❌ | ❌ | ✅ |
| **Moodle XML Export (LMS)** | ❌ | ❌ | ✅ |

> **Note**: LMS export formats (QTI 2.1 and Moodle XML) are **Pro-only** features to serve educators and institutions who need LMS integration.

---

## Current Database Schema (Actual)

> **⚠️ IMPORTANT**: The original prompt assumed an `options` table exists. Quizify uses a **JSONB column structure** instead. The epics below reflect the actual schema.

### Quizzes Table
```sql
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    created_by UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    content_source_type TEXT DEFAULT 'file' CHECK (content_source_type IN ('file', 'url', 'text')),
    content_source_reference TEXT
);
```

### Questions Table
```sql
CREATE TABLE questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID REFERENCES quizzes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- 'multiple_choice', 'true_false', 'fill_blank', 'matching'
    question TEXT NOT NULL,
    options JSONB,        -- For MCQ/fill_blank: ["Option A", "Option B", ...]
    left JSONB,           -- For matching: ["Left 1", "Left 2", ...]
    right JSONB,          -- For matching: ["Right 1", "Right 2", ...]
    correct_answer JSONB, -- MCQ: "A", T/F: true/false, Fill: "answer", Matching: [0, 2, 1, 3]
    explanation TEXT,
    source TEXT           -- Source text excerpt
);
```

### Question Types & Data Structure
| Type | `options` | `left` | `right` | `correct_answer` |
|------|-----------|--------|---------|------------------|
| `multiple_choice` | `["A", "B", "C", "D"]` | null | null | `"B"` |
| `true_false` | null | null | null | `true` or `false` |
| `fill_blank` | `["word1", "word2", ...]` | null | null | `"correct_word"` |
| `matching` | null | `["Left1", "Left2"]` | `["Right1", "Right2"]` | `[0, 1]` (indices) |

---

## Epic Overview

| Epic | Title | Tier Access | Priority | Estimated Effort |
|------|-------|-------------|----------|------------------|
| E1 | Export Infrastructure & Strategy Pattern | All | P0 - Critical | 3-4 days |
| E2 | PDF Export Implementation | All | P0 - Critical | 2-3 days |
| E3 | DOCX Export Implementation | All | P0 - Critical | 2 days |
| E4 | CSV Exports (Quizify Native + Anki) | All | P1 - High | 2 days |
| E5 | Share Link Feature | All | P1 - High | 3-4 days |
| E6 | QTI 2.1 Export (LMS) | **Pro Only** | P2 - Medium | 3 days |
| E7 | Moodle XML Export (LMS) | **Pro Only** | P2 - Medium | 2-3 days |
| E8 | Frontend Export UI | All (with tier checks) | P1 - High | 3-4 days |

**Total Estimated Effort**: 20-27 days

---

## Epic 1: Export Infrastructure & Strategy Pattern

### Overview
Build the foundational export system using the strategy pattern, enabling clean extension for future formats.

### User Stories

**E1-US1**: As a developer, I want a unified export API endpoint so that all export formats are accessed consistently.

**E1-US2**: As a developer, I want a strategy pattern implementation so that adding new export formats requires minimal code changes.

**E1-US3**: As a user, I want proper error messages when export fails so that I understand what went wrong.

### Technical Tasks

#### E1-T1: Create Export Route Handler
```
File: api/export_routes.py
- POST /api/quizzes/{quiz_id}/export
- Request body: { "format": "pdf|docx|csv_quizify|csv_anki|qti|moodle_xml|share_link", "include_answer_key": bool, "include_explanations": bool }
- Auth required via Bearer token
- Tier validation: QTI and Moodle XML require Pro tier
- Returns file download or JSON (share_link)
```

#### E1-T1b: Create Tier Validation Middleware
```
File: services/exporters/tier_validator.py
- PRO_ONLY_FORMATS = ["qti", "moodle_xml"]
- validate_export_tier_access(user_tier: str, format: str) -> bool
- Raises 403 HTTPException if tier insufficient
- Error message: "LMS export formats require a Pro subscription"
```

#### E1-T2: Create Export Request/Response Schemas
```
File: schemas/export.py
- ExportRequest: format, include_answer_key, include_explanations
- ExportFormat: Enum of supported formats
- ExportResponse: For share_link JSON response
- QuizExportData: Internal model for quiz + questions
```

#### E1-T3: Create Base Exporter Interface
```
File: services/exporters/base.py
- Abstract BaseExporter class
- Abstract method: export(quiz_data: QuizExportData, options: ExportOptions) -> ExportResult
- ExportResult: bytes (file content), content_type, filename
```

#### E1-T4: Create Export Handler with Strategy Pattern
```
File: handlers/export_handler.py
- ExportHandlerFactory: Returns appropriate exporter based on format
- validate_quiz_ownership(quiz_id, user_id) -> Quiz
- validate_tier_access(user_id, format) -> None (raises 403 if insufficient)
- load_quiz_with_questions(quiz_id) -> QuizExportData
- export_quiz(quiz_id, user_id, user_tier, format, options) -> Response
```

#### E1-T5: Create Quiz Data Loader Service
```
File: services/exporters/quiz_loader.py
- Load quiz from DB with all questions
- Transform JSONB fields to structured Python objects
- Handle all question types uniformly
```

### Acceptance Criteria
- [ ] Export endpoint returns 401 if unauthenticated
- [ ] Export endpoint returns 403 if quiz not owned by user
- [ ] Export endpoint returns 403 if tier insufficient for LMS formats (QTI/Moodle)
- [ ] Export endpoint returns 404 if quiz not found
- [ ] Export endpoint returns 422 if invalid format
- [ ] Export endpoint returns 500 with safe message for unexpected errors
- [ ] Strategy pattern allows easy addition of new exporters
- [ ] Quiz loader correctly parses all question types
- [ ] Free/Basic users cannot access QTI or Moodle XML exports
- [ ] Pro users can access all export formats

### Dependencies
- None (foundational epic)

### Test Requirements
- Unit tests for quiz loader with all question types
- Unit tests for error handling (401, 403, 404, 422, 500)
- Unit tests for tier validation (free->qti=403, basic->qti=403, pro->qti=200)
- Integration test for export endpoint routing

---

## Epic 2: PDF Export Implementation

### Overview
Generate printable PDF quizzes with professional formatting for tests and worksheets.

### User Stories

**E2-US1**: As a teacher, I want to export my quiz as a PDF so that I can print it for classroom tests.

**E2-US2**: As a user, I want the PDF to include an answer key section so that I can grade quizzes easily.

**E2-US3**: As a user, I want explanations included optionally so that students can learn from their mistakes.

### Technical Tasks

#### E2-T1: Install PDF Generation Dependencies
```
Requirements:
- weasyprint>=60.0 (HTML to PDF)
- jinja2>=3.0 (HTML templating)

Add to requirements.txt:
weasyprint>=60.0
```

#### E2-T2: Create PDF HTML Templates
```
File: services/exporters/templates/pdf/
- quiz_template.html: Main quiz layout
- question_mcq.html: Multiple choice rendering
- question_tf.html: True/false rendering
- question_fill.html: Fill-in-the-blank rendering
- question_matching.html: Two-column matching layout
- answer_key.html: Answer key section
- styles.css: Print-optimized CSS
```

#### E2-T3: Implement PDF Exporter
```
File: services/exporters/pdf_exporter.py
- PdfExporter(BaseExporter)
- render_quiz_html(quiz_data, options) -> str
- render_question(question) -> str (delegates by type)
- render_answer_key(questions, include_explanations) -> str
- export() -> ExportResult with application/pdf
```

#### E2-T4: PDF Layout Requirements
```
Cover Section:
- Quiz title (large, centered)
- Description (if available)
- Metadata: subject, difficulty, question count
- Date generated

Questions Section:
- Numbered (1., 2., 3., ...)
- MCQ: Question text + A, B, C, D options
- True/False: Question + "True / False" line
- Fill-blank: Question with ____ blanks
- Matching: Two-column layout with letters/numbers

Answer Key (optional):
- Separate section at end
- Numbered answers
- Explanations if include_explanations=true
```

### Acceptance Criteria
- [ ] PDF renders correctly for all question types
- [ ] Pagination is clean (no questions split across pages)
- [ ] Answer key is on separate page(s) when included
- [ ] No raw IDs or DB fields visible
- [ ] UTF-8 characters render correctly (math symbols, accents)
- [ ] File downloads with correct Content-Type and filename

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for each question type rendering
- Test PDF generation with mixed question types
- Test with special characters (UTF-8)
- Test with/without answer key
- Test with/without explanations

---

## Epic 3: DOCX Export Implementation

### Overview
Generate editable Word documents for teachers who want to customize quizzes.

### User Stories

**E3-US1**: As a teacher, I want to export my quiz as a Word document so that I can edit questions before printing.

**E3-US2**: As a user, I want the DOCX to have proper formatting so that it looks professional in Word/Google Docs.

### Technical Tasks

#### E3-T1: Install DOCX Dependencies
```
Add to requirements.txt:
python-docx>=1.1.0
```

#### E3-T2: Implement DOCX Exporter
```
File: services/exporters/docx_exporter.py
- DocxExporter(BaseExporter)
- create_document() -> Document
- add_title_section(doc, quiz_data)
- add_question(doc, question, number)
- add_mcq_question(doc, question, number)
- add_tf_question(doc, question, number)
- add_fill_question(doc, question, number)
- add_matching_question(doc, question, number)
- add_answer_key(doc, questions, include_explanations)
- export() -> ExportResult with application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

#### E3-T3: DOCX Layout Requirements
```
Document Structure:
- Title as Heading 1
- Description as normal paragraph
- Questions as numbered list
- MCQ options as lettered sub-list (A., B., C., D.)
- Matching as two-column table
- Answer Key section at end with Heading 2
```

### Acceptance Criteria
- [ ] DOCX opens correctly in Microsoft Word
- [ ] DOCX opens correctly in Google Docs
- [ ] All question types render sensibly
- [ ] Formatting is clean and professional
- [ ] Answer key at end of document

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for each question type formatting
- Test DOCX generation with all question types
- Validate DOCX file structure is valid

---

## Epic 4: CSV Exports (Quizify Native + Anki)

### Overview
Implement two CSV formats: Quizify native for data portability and Anki format for spaced repetition learning.

### User Stories

**E4-US1**: As a power user, I want to export my quiz in CSV format so that I can edit questions in a spreadsheet.

**E4-US2**: As a student, I want to export my quiz in Anki format so that I can study with flashcards.

### Technical Tasks

#### E4-T1: Implement Quizify CSV Exporter
```
File: services/exporters/csv_quizify_exporter.py
- CsvQuizifyExporter(BaseExporter)

CSV Columns:
- quiz_title
- question_id
- question_order
- question_type
- question_prompt
- option_label (A, B, C, D for MCQ; left/right for matching)
- option_text
- is_correct
- answer_text (for fill_blank, T/F)
- explanation
- metadata_json

Row Strategy:
- MCQ: One row per option (4 rows per question)
- True/False: Single row with answer_text = "True"/"False"
- Fill-blank: Single row with answer_text = correct answer
- Matching: One row per pair
```

#### E4-T2: Implement Anki CSV Exporter
```
File: services/exporters/csv_anki_exporter.py
- CsvAnkiExporter(BaseExporter)

CSV Format:
- Two columns only: Front, Back
- Tab-separated or comma-separated

Card Mapping:
- MCQ: Front = "Question\nA. opt1\nB. opt2..." | Back = "Correct: B. answer\n\nExplanation: ..."
- True/False: Front = Question | Back = "True/False\n\nExplanation: ..."
- Fill-blank: Front = Question with ____ | Back = "Answer: X\n\nExplanation: ..."
- Matching: One card per pair (Front = left term, Back = right term)
```

#### E4-T3: CSV Utility Functions
```
File: services/exporters/csv_utils.py
- escape_csv_value(value) -> str
- format_multiline_html(text) -> str (for Anki)
- ensure_utf8_bom(content) -> bytes (for Excel compatibility)
```

### Acceptance Criteria
- [ ] CSV files are valid and open in Excel/Google Sheets
- [ ] UTF-8 encoding with BOM for Excel compatibility
- [ ] Comma-safe handling (proper escaping)
- [ ] Anki CSV imports successfully in Anki desktop
- [ ] All question types export correctly

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for CSV escaping
- Test Quizify CSV with all question types
- Test Anki CSV with all question types
- Verify CSV can be re-imported (future feature)

---

## Epic 5: Share Link Feature

### Overview
Enable users to share read-only quiz pages via public URLs.

### User Stories

**E5-US1**: As a teacher, I want to share my quiz via a link so that students can access it without logging in.

**E5-US2**: As a viewer, I want to see a clean quiz page so that I can practice or review.

**E5-US3**: As a quiz owner, I want to revoke sharing so that I can make my quiz private again.

### Technical Tasks

#### E5-T1: Database Migration for Share Link
```
File: migrations/019_add_share_link_columns.sql

ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS public_slug TEXT UNIQUE;

CREATE INDEX IF NOT EXISTS idx_quizzes_public_slug ON quizzes(public_slug) WHERE is_public = TRUE;

-- RLS Policy for public access
CREATE POLICY quizzes_public_read_policy 
ON quizzes FOR SELECT 
USING (is_public = TRUE);
```

#### E5-T2: Create Share Link Service
```
File: services/share_service.py
- generate_public_slug() -> str (10-16 char random, URL-safe)
- create_share_link(quiz_id, user_id) -> str (public URL)
- revoke_share_link(quiz_id, user_id) -> None
- get_quiz_by_slug(slug) -> QuizPublicView | None
```

#### E5-T3: Create Share API Endpoints
```
File: api/share_routes.py

POST /api/quizzes/{quiz_id}/share
- Auth required
- Generates slug if not exists, sets is_public=true
- Response: { "share_url": "https://app.quizify.ca/share/{slug}" }

DELETE /api/quizzes/{quiz_id}/share
- Auth required
- Sets is_public=false (keeps slug for potential re-enable)
- Response: 204 No Content

GET /api/quizzes/public/{public_slug}
- No auth required
- Returns quiz + questions in safe format (no user PII)
- Response: QuizPublicView
```

#### E5-T4: Create Public Quiz Schema
```
File: schemas/share.py
- ShareLinkRequest: (empty, just uses quiz_id from path)
- ShareLinkResponse: share_url
- QuizPublicView: id, title, description, questions (sanitized)
- QuestionPublicView: question fields without internal IDs
```

#### E5-T5: Security Requirements
```
Security Checklist:
- [ ] Slug is cryptographically random (secrets.token_urlsafe)
- [ ] No user_id, email, or PII in public response
- [ ] No internal database IDs exposed
- [ ] Rate limiting on public endpoint
- [ ] Quiz owner can always revoke access
```

### Acceptance Criteria
- [ ] Share link generates unique, non-guessable slug
- [ ] Public endpoint returns quiz without authentication
- [ ] No private user data exposed in public response
- [ ] Owner can revoke sharing
- [ ] Re-enabling share uses same slug
- [ ] Works with all question types

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for slug generation (uniqueness, format)
- Integration tests for share/unshare flow
- Security tests for PII leakage
- Test public endpoint with invalid slugs

---

## Epic 6: QTI 2.1 Export (LMS)

> **🔒 PRO TIER ONLY**: This feature is restricted to Pro subscribers.

### Overview
Enable export to QTI 2.1 XML format for LMS platforms like Canvas and Blackboard.

### User Stories

**E6-US1**: As a **Pro** educator, I want to export my quiz in QTI format so that I can import it into my school's LMS.

**E6-US2**: As an LMS administrator, I want valid QTI files so that imports work without errors.

**E6-US3**: As a Basic user, I want to see an upgrade prompt when I try to use LMS export so that I understand the value of Pro.

### Technical Tasks

#### E6-T1: Research QTI 2.1 Specification
```
Reference: IMS Global QTI 2.1 Implementation Guide
Key Elements:
- <assessmentTest> or <assessmentItem>
- <choiceInteraction> for MCQ
- <textEntryInteraction> for fill-blank
- <matchInteraction> for matching
- <responseDeclaration> for correct answers
- <outcomeDeclaration> for scoring
```

#### E6-T2: Implement QTI Exporter
```
File: services/exporters/qti_exporter.py
- QtiExporter(BaseExporter)
- build_assessment_xml(quiz_data) -> ElementTree
- build_mcq_item(question) -> Element
- build_tf_item(question) -> Element
- build_fill_item(question) -> Element
- build_matching_item(question) -> Element
- export() -> ExportResult with application/xml
```

#### E6-T3: QTI XML Structure
```xml
<?xml version="1.0" encoding="UTF-8"?>
<assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1"
                identifier="quiz_{id}" title="{title}">
  <testPart identifier="part1">
    <assessmentSection identifier="section1">
      <assessmentItemRef identifier="q1" href="item_q1.xml"/>
      ...
    </assessmentSection>
  </testPart>
</assessmentTest>
```

### Acceptance Criteria
- [ ] QTI XML is well-formed and valid UTF-8
- [ ] MCQ questions import correctly in Canvas
- [ ] True/False questions work as 2-option choice
- [ ] Fill-blank uses textEntryInteraction
- [ ] Matching uses matchInteraction
- [ ] Correct answers are properly encoded
- [ ] Basic scoring metadata included

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for each question type XML generation
- XML schema validation tests
- Integration test with sample LMS import (manual verification)

---

## Epic 7: Moodle XML Export

> **🔒 PRO TIER ONLY**: This feature is restricted to Pro subscribers.

### Overview
Enable direct import of quizzes into Moodle LMS.

### User Stories

**E7-US1**: As a **Pro** Moodle user, I want to export my quiz in Moodle XML format so that I can import it directly.

**E7-US2**: As a Basic user, I want to see an upgrade prompt when I try to use Moodle export so that I understand the value of Pro.

### Technical Tasks

#### E7-T1: Research Moodle XML Format
```
Reference: Moodle XML Format Documentation
Key Elements:
- <quiz> root element
- <question type="multichoice|truefalse|shortanswer|match">
- <name><text>Question Title</text></name>
- <questiontext format="html"><text>...</text></questiontext>
- <answer fraction="100|0"><text>...</text></answer>
- <feedback><text>Explanation here</text></feedback>
```

#### E7-T2: Implement Moodle XML Exporter
```
File: services/exporters/moodle_exporter.py
- MoodleXmlExporter(BaseExporter)
- build_quiz_xml(quiz_data) -> ElementTree
- build_multichoice_question(question) -> Element
- build_truefalse_question(question) -> Element
- build_shortanswer_question(question) -> Element (for fill-blank)
- build_match_question(question) -> Element
- export() -> ExportResult with application/xml
```

#### E7-T3: Moodle XML Structure
```xml
<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="multichoice">
    <name><text>Q1</text></name>
    <questiontext format="html">
      <text><![CDATA[What is X?]]></text>
    </questiontext>
    <answer fraction="0"><text>Option A</text></answer>
    <answer fraction="100"><text>Option B</text></answer>
    <answer fraction="0"><text>Option C</text></answer>
    <answer fraction="0"><text>Option D</text></answer>
    <generalfeedback><text>Explanation...</text></generalfeedback>
  </question>
</quiz>
```

### Acceptance Criteria
- [ ] Moodle XML is well-formed and valid UTF-8
- [ ] File can be imported in Moodle without errors
- [ ] MCQ uses `type="multichoice"` with correct fractions
- [ ] True/False uses `type="truefalse"`
- [ ] Fill-blank uses `type="shortanswer"`
- [ ] Matching uses `type="match"` with subquestions
- [ ] Feedback/explanations included when available

### Dependencies
- Epic 1 (Export Infrastructure)

### Test Requirements
- Unit tests for each question type XML generation
- XML well-formedness tests
- Integration test with Moodle import (manual verification)

---

## Epic 8: Frontend Export UI

### Overview
Implement the export UI in the Next.js frontend using shadcn/ui components.

### User Stories

**E8-US1**: As a user, I want an Export button on my quiz so that I can access export options easily.

**E8-US2**: As a user, I want to see a loading indicator during export so that I know the system is working.

**E8-US3**: As a user, I want to copy the share link easily so that I can send it to others.

### Technical Tasks

#### E8-T1: Create Export Dialog Component
```
File: components/quiz/ExportDialog.tsx
- Trigger button: "Export"
- Dialog with export format options
- Checkboxes: Include Answer Key, Include Explanations
- Format buttons: PDF, DOCX, CSV, Anki (available to all tiers)
- LMS section with tier gate:
  - QTI, Moodle XML buttons
  - If user is Pro: buttons enabled
  - If user is Free/Basic: buttons show lock icon + "Pro" badge
  - Clicking locked button shows upgrade modal/toast
- Share Link section with copy button
```

#### E8-T1b: Create Upgrade Prompt Component
```
File: components/billing/UpgradePrompt.tsx
- Modal or inline prompt for upgrading
- Message: "LMS exports are available on the Pro plan"
- CTA button: "Upgrade to Pro" -> links to billing page
- Dismissible
```

#### E8-T2: Create Export API Client
```
File: lib/api/export.ts
- exportQuiz(quizId, format, options) -> Blob | ShareResponse
- createShareLink(quizId) -> ShareResponse
- revokeShareLink(quizId) -> void
- Handle file downloads with proper filename
```

#### E8-T3: Create Share Link Panel
```
File: components/quiz/ShareLinkPanel.tsx
- Display share URL
- Copy to clipboard button
- Open in new tab button
- Toggle to revoke/enable sharing
```

#### E8-T4: Create Public Quiz Page
```
File: app/share/[slug]/page.tsx
- Fetch quiz via public API
- Render quiz in read-only, exam-like view
- No edit/delete actions
- Optional "Start Practice" mode
- Responsive design
```

#### E8-T5: Loading and Error States
```
UI Requirements:
- Loading spinner during export generation
- Toast notifications for success/error
- Disable buttons during processing
- Handle network errors gracefully
```

### Acceptance Criteria
- [ ] Export button visible on quiz detail page
- [ ] All export formats accessible from dialog (with tier restrictions)
- [ ] File downloads with sensible filename: `{quiz-title}-{format}.{ext}`
- [ ] Share link copyable with one click
- [ ] Loading states prevent double-clicks
- [ ] Error messages shown via toast
- [ ] Public quiz page is responsive
- [ ] Public quiz page has no editing capabilities
- [ ] LMS export buttons (QTI, Moodle) show lock icon for Free/Basic users
- [ ] Clicking locked LMS export shows upgrade prompt
- [ ] Pro users see all export options enabled
- [ ] Upgrade prompt links to billing/subscription page

### Dependencies
- Epics 1-7 (All backend export implementations)
- Billing service for tier detection

### Test Requirements
- Component tests for ExportDialog
- Component tests for tier-gated UI (Free, Basic, Pro states)
- Integration tests for export flow
- E2E test for share link generation and viewing
- E2E test for upgrade flow from export dialog

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
- Epic 1: Export Infrastructure
- Epic 5: Share Link (DB migration)

### Phase 2: Ship Quickly Formats (Week 2)
- Epic 2: PDF Export
- Epic 3: DOCX Export
- Epic 4: CSV Exports

### Phase 3: LMS Formats (Week 3)
- Epic 6: QTI 2.1 Export
- Epic 7: Moodle XML Export

### Phase 4: Frontend Integration (Week 4)
- Epic 8: Frontend Export UI
- Epic 5: Share Link (Complete)

---

## Dependencies Diagram

```
                    ┌─────────────────┐
                    │  Epic 1         │
                    │  Infrastructure │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
    ┌───────────┐      ┌───────────┐      ┌───────────┐
    │  Epic 2   │      │  Epic 3   │      │  Epic 4   │
    │  PDF      │      │  DOCX     │      │  CSV      │
    │  (All)    │      │  (All)    │      │  (All)    │
    └───────────┘      └───────────┘      └───────────┘
          │                  │                  │
          │                  │                  │
          │                  │                  │
    ┌───────────┐      ┌───────────┐            │
    │  Epic 6   │      │  Epic 7   │            │
    │  QTI 2.1  │      │  Moodle   │            │
    │  (PRO)    │      │  (PRO)    │            │
    └───────────┘      └───────────┘            │
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Epic 5         │
                    │  Share Link     │
                    │  (All)          │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Epic 8         │
                    │  Frontend UI    │
                    │  (Tier-Aware)   │
                    └─────────────────┘
```

---

## Tier Enforcement Implementation

### Backend Enforcement (Critical)

```python
# services/exporters/tier_validator.py

from fastapi import HTTPException
from typing import Literal

ExportFormat = Literal["pdf", "docx", "csv_quizify", "csv_anki", "qti", "moodle_xml", "share_link"]

# Formats restricted to Pro tier only
PRO_ONLY_FORMATS = {"qti", "moodle_xml"}

def validate_export_tier_access(user_tier: str, export_format: ExportFormat) -> None:
    """
    Validates that user's tier allows the requested export format.
    
    Raises:
        HTTPException 403 if tier insufficient for requested format
    """
    if export_format in PRO_ONLY_FORMATS and user_tier != "pro":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_insufficient",
                "message": "LMS export formats (QTI, Moodle XML) require a Pro subscription",
                "required_tier": "pro",
                "current_tier": user_tier,
                "upgrade_url": "/billing/upgrade"
            }
        )
```

### Frontend Enforcement (UX)

```typescript
// lib/export/tierAccess.ts

export const PRO_ONLY_FORMATS = ['qti', 'moodle_xml'] as const;

export function canAccessFormat(userTier: string, format: string): boolean {
  if (PRO_ONLY_FORMATS.includes(format as any)) {
    return userTier === 'pro';
  }
  return true;
}

export function getFormatTierBadge(format: string): 'pro' | null {
  return PRO_ONLY_FORMATS.includes(format as any) ? 'pro' : null;
}
```

### API Response for Tier Restriction

```json
// 403 Response when Free/Basic user tries LMS export
{
  "detail": {
    "error": "tier_insufficient",
    "message": "LMS export formats (QTI, Moodle XML) require a Pro subscription",
    "required_tier": "pro",
    "current_tier": "basic",
    "upgrade_url": "/billing/upgrade"
  }
}
```

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| PDF rendering issues with complex questions | Medium | High | Use HTML templating with WeasyPrint; test extensively |
| QTI/Moodle XML compatibility issues | Medium | Medium | Test with actual LMS; implement only core features first |
| Large quiz export performance | Low | Medium | Stream file generation; add progress indicators |
| Share link security vulnerabilities | Low | High | Use cryptographically secure slugs; security review |
| Browser download handling inconsistencies | Medium | Low | Test across browsers; use standard Content-Disposition |
| Users bypassing tier checks via API | Low | High | Enforce tier check at handler level, not just UI |
| Tier confusion in upgrade prompts | Medium | Low | Clear messaging about what Pro unlocks |

---

## Success Metrics

1. **Export Completion Rate**: >95% of export requests complete successfully
2. **PDF Quality**: Zero customer complaints about formatting
3. **LMS Import Success**: QTI/Moodle files import without modification
4. **Share Link Usage**: Track share link creation and view counts
5. **Export Format Distribution**: Monitor which formats are most popular
6. **Pro Conversion from Export**: Track upgrades triggered by LMS export prompts

---

## Out of Scope (Future Considerations)

- [ ] Bulk export (multiple quizzes at once)
- [ ] Custom PDF templates/branding
- [ ] Import from CSV/QTI/Moodle XML
- [ ] Export scheduling/automation
- [ ] Export to Google Forms
- [ ] Password-protected share links
- [ ] Time-limited share links
- [ ] Analytics on shared quiz views

---

## Appendix: File Structure

```
quizify/
├── api/
│   ├── export_routes.py          # Epic 1
│   └── share_routes.py           # Epic 5
├── handlers/
│   └── export_handler.py         # Epic 1
├── schemas/
│   ├── export.py                 # Epic 1
│   └── share.py                  # Epic 5
├── services/
│   ├── share_service.py          # Epic 5
│   └── exporters/
│       ├── __init__.py
│       ├── base.py               # Epic 1
│       ├── quiz_loader.py        # Epic 1
│       ├── pdf_exporter.py       # Epic 2
│       ├── docx_exporter.py      # Epic 3
│       ├── csv_quizify_exporter.py  # Epic 4
│       ├── csv_anki_exporter.py  # Epic 4
│       ├── csv_utils.py          # Epic 4
│       ├── qti_exporter.py       # Epic 6 (Pro Only)
│       ├── moodle_exporter.py    # Epic 7 (Pro Only)
│       ├── tier_validator.py     # Epic 1 - Tier access control
│       └── templates/
│           └── pdf/              # Epic 2
│               ├── quiz_template.html
│               ├── question_mcq.html
│               ├── question_tf.html
│               ├── question_fill.html
│               ├── question_matching.html
│               ├── answer_key.html
│               └── styles.css
├── migrations/
│   └── 019_add_share_link_columns.sql  # Epic 5
└── tests/
    ├── test_export_api.py        # Epic 1
    ├── test_tier_validator.py    # Epic 1 - Tier access tests
    ├── test_pdf_exporter.py      # Epic 2
    ├── test_docx_exporter.py     # Epic 3
    ├── test_csv_exporters.py     # Epic 4
    ├── test_share_service.py     # Epic 5
    ├── test_qti_exporter.py      # Epic 6 (Pro Only)
    └── test_moodle_exporter.py   # Epic 7 (Pro Only)
```

---

*Document Version: 1.1.0*  
*Last Updated: 2025-11-25*  
*Change: Added tier-based access control - LMS exports (QTI, Moodle XML) are Pro-only*
