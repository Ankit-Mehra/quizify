# Frontend Flashcard Integration Guide

> **Version**: 1.0.0  
> **Last Updated**: December 25, 2025  
> **API Base URL**: `/api/flashcards`

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Credit System](#credit-system)
4. [Generation Endpoints](#generation-endpoints)
   - [Generate from Text](#1-generate-flashcards-from-text)
   - [Generate from File](#2-generate-flashcards-from-file)
   - [Generate from URL](#3-generate-flashcards-from-url)
5. [Deck Management](#deck-management)
   - [List User Decks](#4-list-user-decks)
   - [Get Deck with Cards](#5-get-deck-with-cards)
   - [Update Deck](#6-update-deck)
   - [Delete Deck](#7-delete-deck)
6. [Card Management](#card-management)
   - [Update Card](#8-update-card)
   - [Delete Card](#9-delete-card)
7. [Study Sessions](#study-sessions)
   - [Start Study Session](#10-start-study-session)
   - [Complete Study Session](#11-complete-study-session)
8. [Export Endpoints](#export-endpoints)
   - [Export Deck](#12-export-deck)
9. [TypeScript Interfaces](#typescript-interfaces)
10. [Error Handling](#error-handling)
11. [Generation Modes Explained](#generation-modes-explained)
12. [UI Implementation Guide](#ui-implementation-guide)
13. [Example Flows](#example-flows)

---

## Overview

The Flashcard API provides AI-powered flashcard generation from multiple content sources (text, files, URLs) with two generation modes:

| Mode | Cost | Speed | Quality | Use Case |
|------|------|-------|---------|----------|
| **Standard** | 1 credit | Fast (~5-15s) | Good | Quick study material, basic memorization |
| **Enhanced** | 2 credits | Slower (~20-45s) | Premium | Deep learning, exam prep, concept mastery |

### Key Features
- 🎴 **Multi-source Generation**: Text, PDF, DOCX, TXT files, and web URLs
- 🧠 **Two Generation Modes**: Standard (fast) and Enhanced (RAG-based)
- 📚 **Spaced Repetition**: Built-in support for SM-2 algorithm fields
- 📤 **Export**: Anki-compatible CSV and printable PDF formats
- ✏️ **CRUD Operations**: Full deck and card management

---

## Authentication

All endpoints require a valid JWT token in the `Authorization` header.

```typescript
const headers = {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
};
```

### Token Refresh
If you receive a `401 Unauthorized` response, refresh the token using Supabase Auth:

```typescript
const { data, error } = await supabase.auth.refreshSession();
if (data?.session) {
  accessToken = data.session.access_token;
}
```

---

## Credit System

### Credit Costs

| Operation | Standard Mode | Enhanced Mode |
|-----------|---------------|---------------|
| Generate Flashcards (Text) | 1 credit | 2 credits |
| Generate Flashcards (File) | 1 credit | 2 credits |
| Generate Flashcards (URL) | 1 credit | 2 credits |
| Export Deck | Free | Free |
| Study Session | Free | Free |

### Pre-Generation Credit Check

Before calling generation endpoints, check user's available credits:

```typescript
// GET /api/billing/state
const billingState = await fetch('/api/billing/state', { headers });
const { available_credits, plan } = await billingState.json();

const requiredCredits = mode === 'enhanced' ? 2 : 1;
if (available_credits < requiredCredits) {
  // Show upgrade prompt or insufficient credits modal
}
```

### Insufficient Credits Response (HTTP 402)

```json
{
  "detail": {
    "error": "insufficient_credits",
    "message": "Not enough credits for enhanced flashcard generation.",
    "available_credits": 1,
    "required_credits": 2,
    "plan": "free"
  }
}
```

---

## Generation Endpoints

### 1. Generate Flashcards from Text

**Endpoint**: `POST /api/flashcards/generate/text`

#### Request Body

```typescript
interface TextFlashcardRequest {
  content: string;           // Min 50 characters
  title?: string;            // Optional deck title
  config: FlashcardGenerationConfig;
}

interface FlashcardGenerationConfig {
  num_cards?: number;        // 1-100, null for auto-calculation
  include_hints: boolean;    // Default: false
  card_style: 'question_answer' | 'term_definition' | 'cloze' | 'mixed';  // Default: 'mixed'
  difficulty: 'easy' | 'medium' | 'hard' | 'mixed';  // Default: 'mixed'
  mode: 'standard' | 'enhanced';  // Default: 'standard'
}
```

#### Example Request

```typescript
const response = await fetch('/api/flashcards/generate/text', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    content: "Photosynthesis is the process by which plants convert sunlight, water, and carbon dioxide into glucose and oxygen. The light-dependent reactions occur in the thylakoid membranes, where chlorophyll absorbs light energy...",
    title: "Biology - Photosynthesis",
    config: {
      num_cards: 10,
      include_hints: true,
      card_style: "question_answer",
      difficulty: "medium",
      mode: "enhanced"
    }
  })
});
```

#### Response (FlashcardGenerationResponse)

```json
{
  "deck_id": "550e8400-e29b-41d4-a716-446655440000",
  "deck_title": "Biology - Photosynthesis",
  "cards": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "deck_id": "550e8400-e29b-41d4-a716-446655440000",
      "front": "What is the primary function of photosynthesis in plants?",
      "back": "To convert sunlight, water, and carbon dioxide into glucose (sugar) and oxygen, providing energy for the plant.",
      "hint": "Think about what plants need from their environment",
      "position": 0,
      "status": "new",
      "ease_factor": 2.5,
      "interval_days": 0,
      "repetitions": 0,
      "next_review": null,
      "concept_name": "Photosynthesis Function",
      "bloom_level": "understand",
      "difficulty_score": 0.35,
      "source_chunk_id": "chunk_abc123",
      "created_at": "2025-12-25T10:30:00Z",
      "updated_at": null
    }
    // ... more cards
  ],
  "card_count": 10,
  "content_source_type": "text",
  "generation_time_ms": 23456,
  "estimated_study_time_minutes": 3,
  "generation_mode": "enhanced",
  "generation_stats": {
    "concepts_extracted": 8,
    "chunks_processed": 12,
    "cards_per_concept": 1.25,
    "bloom_distribution": {
      "remember": 2,
      "understand": 4,
      "apply": 3,
      "analyze": 1
    }
  },
  "credits_consumed": 2
}
```

---

### 2. Generate Flashcards from File

**Endpoint**: `POST /api/flashcards/generate/file`

#### Prerequisites
File must be uploaded first via `/api/files/upload` endpoint.

**Supported File Types**: PDF, DOCX, TXT  
**Max File Size**: 10MB

#### Request Body

```typescript
interface FileFlashcardRequest {
  file_id: string;           // UUID from file upload
  title?: string;            // Optional deck title
  config: FlashcardGenerationConfig;
}
```

#### Example Request

```typescript
// Step 1: Upload file first
const formData = new FormData();
formData.append('file', pdfFile);
const uploadResponse = await fetch('/api/files/upload', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${accessToken}` },
  body: formData
});
const { file_id } = await uploadResponse.json();

// Step 2: Generate flashcards
const response = await fetch('/api/flashcards/generate/file', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    file_id: file_id,
    title: "Chemistry Chapter 5",
    config: {
      num_cards: 20,
      include_hints: false,
      card_style: "mixed",
      difficulty: "mixed",
      mode: "standard"
    }
  })
});
```

#### Response
Same structure as `FlashcardGenerationResponse` above, with `content_source_type: "file"`.

---

### 3. Generate Flashcards from URL

**Endpoint**: `POST /api/flashcards/generate/url`

#### Request Body

```typescript
interface UrlFlashcardRequest {
  url: string;               // Valid HTTP/HTTPS URL
  title?: string;            // Optional deck title
  config: FlashcardGenerationConfig;
}
```

#### Example Request

```typescript
const response = await fetch('/api/flashcards/generate/url', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    url: "https://en.wikipedia.org/wiki/Machine_learning",
    title: "Machine Learning Basics",
    config: {
      num_cards: 15,
      include_hints: true,
      card_style: "term_definition",
      difficulty: "easy",
      mode: "enhanced"
    }
  })
});
```

#### Response
Same structure as `FlashcardGenerationResponse` above, with `content_source_type: "url"`.

#### URL Restrictions
- Must be publicly accessible (no login-required pages)
- JavaScript-rendered content is supported (uses headless browser)
- Blocked: Private IPs, localhost, internal networks (SSRF protection)

---

## Deck Management

### 4. List User Decks

**Endpoint**: `GET /api/flashcards/decks`

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Max decks to return (1-100) |
| `offset` | integer | 0 | Pagination offset |

#### Example Request

```typescript
const response = await fetch('/api/flashcards/decks?limit=20&offset=0', {
  method: 'GET',
  headers
});
```

#### Response (Deck[])

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "created_by": "user-uuid-here",
    "title": "Biology - Photosynthesis",
    "description": null,
    "card_count": 10,
    "content_source_type": "text",
    "content_source_reference": null,
    "created_at": "2025-12-25T10:30:00Z",
    "updated_at": null,
    "last_studied": "2025-12-25T14:00:00Z"
  }
  // ... more decks
]
```

---

### 5. Get Deck with Cards

**Endpoint**: `GET /api/flashcards/decks/{deck_id}`

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `deck_id` | UUID | ID of the deck |

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_cards` | boolean | true | Include all cards in response |

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/decks/${deckId}?include_cards=true`, {
  method: 'GET',
  headers
});
```

#### Response (DeckWithCards)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_by": "user-uuid-here",
  "title": "Biology - Photosynthesis",
  "description": "AI-generated flashcards covering photosynthesis concepts",
  "card_count": 10,
  "content_source_type": "text",
  "content_source_reference": null,
  "created_at": "2025-12-25T10:30:00Z",
  "updated_at": null,
  "last_studied": "2025-12-25T14:00:00Z",
  "cards": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "deck_id": "550e8400-e29b-41d4-a716-446655440000",
      "front": "What is photosynthesis?",
      "back": "The process by which plants convert light energy into chemical energy...",
      "hint": "Light + Water + CO2 = ?",
      "position": 0,
      "status": "new",
      "ease_factor": 2.5,
      "interval_days": 0,
      "repetitions": 0,
      "next_review": null,
      "concept_name": "Photosynthesis Definition",
      "bloom_level": "remember",
      "difficulty_score": 0.25,
      "source_chunk_id": null,
      "created_at": "2025-12-25T10:30:00Z",
      "updated_at": null
    }
    // ... more cards
  ]
}
```

---

### 6. Update Deck

**Endpoint**: `PATCH /api/flashcards/decks/{deck_id}`

#### Request Body

```typescript
interface DeckUpdate {
  title?: string;
  description?: string;
}
```

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/decks/${deckId}`, {
  method: 'PATCH',
  headers,
  body: JSON.stringify({
    title: "Biology - Photosynthesis (Updated)",
    description: "Complete study set for Chapter 4"
  })
});
```

#### Response (Deck)
Returns the updated deck object.

---

### 7. Delete Deck

**Endpoint**: `DELETE /api/flashcards/decks/{deck_id}`

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/decks/${deckId}`, {
  method: 'DELETE',
  headers
});
```

#### Response

```json
{
  "message": "Deck deleted successfully",
  "deck_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Note**: Deleting a deck also deletes all associated cards (cascade delete).

---

## Card Management

### 8. Update Card

**Endpoint**: `PATCH /api/flashcards/cards/{card_id}`

#### Request Body

```typescript
interface FlashcardUpdate {
  front?: string;
  back?: string;
  hint?: string;
}
```

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/cards/${cardId}`, {
  method: 'PATCH',
  headers,
  body: JSON.stringify({
    front: "What are the two main stages of photosynthesis?",
    back: "1. Light-dependent reactions (in thylakoids)\n2. Light-independent reactions / Calvin cycle (in stroma)",
    hint: "One needs light directly, one doesn't"
  })
});
```

#### Response (Flashcard)
Returns the updated flashcard object.

---

### 9. Delete Card

**Endpoint**: `DELETE /api/flashcards/cards/{card_id}`

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/cards/${cardId}`, {
  method: 'DELETE',
  headers
});
```

#### Response

```json
{
  "message": "Flashcard deleted successfully",
  "card_id": "660e8400-e29b-41d4-a716-446655440001"
}
```

---

## Study Sessions

### 10. Start Study Session

**Endpoint**: `POST /api/flashcards/study/start`

#### Request Body

```typescript
interface StudySessionStart {
  deck_id: string;           // UUID
  card_limit?: number;       // 1-100, optional
  shuffle: boolean;          // Default: true
  filter_status?: ('new' | 'learning' | 'review' | 'mastered')[];  // Optional filter
}
```

#### Example Request

```typescript
const response = await fetch('/api/flashcards/study/start', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    deck_id: "550e8400-e29b-41d4-a716-446655440000",
    card_limit: 20,
    shuffle: true,
    filter_status: ["new", "learning", "review"]  // Exclude mastered cards
  })
});
```

#### Response (StudySessionResponse)

```json
{
  "session_id": "770e8400-e29b-41d4-a716-446655440002",
  "deck_id": "550e8400-e29b-41d4-a716-446655440000",
  "deck_title": "Biology - Photosynthesis",
  "cards": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "deck_id": "550e8400-e29b-41d4-a716-446655440000",
      "front": "What is photosynthesis?",
      "back": "The process by which plants convert light energy...",
      "hint": "Light + Water + CO2 = ?",
      "position": 0,
      "status": "new",
      "ease_factor": 2.5,
      "interval_days": 0,
      "repetitions": 0,
      "next_review": null,
      "created_at": "2025-12-25T10:30:00Z",
      "updated_at": null
    }
    // ... more cards (shuffled order)
  ],
  "total_cards": 8,
  "new_count": 3,
  "learning_count": 2,
  "review_count": 3
}
```

---

### 11. Complete Study Session

**Endpoint**: `POST /api/flashcards/study/complete`

#### Request Body

```typescript
interface StudySessionComplete {
  session_id: string;        // UUID from start response
  results: CardReviewResult[];
}

interface CardReviewResult {
  card_id: string;           // UUID
  result: 'again' | 'hard' | 'good' | 'easy';
  time_spent_seconds?: number;
}
```

#### Review Result Meanings

| Result | Description | Effect on Card |
|--------|-------------|----------------|
| `again` | Completely forgot | Reset to learning, show again soon |
| `hard` | Struggled to recall | Shorter interval, reduced ease |
| `good` | Recalled correctly | Normal interval progression |
| `easy` | Instant recall | Longer interval, increased ease |

#### Example Request

```typescript
const response = await fetch('/api/flashcards/study/complete', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    session_id: "770e8400-e29b-41d4-a716-446655440002",
    results: [
      { card_id: "660e8400-e29b-41d4-a716-446655440001", result: "good", time_spent_seconds: 12 },
      { card_id: "660e8400-e29b-41d4-a716-446655440002", result: "easy", time_spent_seconds: 5 },
      { card_id: "660e8400-e29b-41d4-a716-446655440003", result: "again", time_spent_seconds: 30 },
      { card_id: "660e8400-e29b-41d4-a716-446655440004", result: "hard", time_spent_seconds: 20 }
    ]
  })
});
```

#### Response (StudySessionSummary)

```json
{
  "session_id": "770e8400-e29b-41d4-a716-446655440002",
  "deck_id": "550e8400-e29b-41d4-a716-446655440000",
  "cards_studied": 4,
  "time_spent_seconds": 67,
  "accuracy_percent": 50.0,
  "cards_mastered": 1,
  "cards_learning": 2,
  "streak_days": 0
}
```

---

## Export Endpoints

### 12. Export Deck

**Endpoint**: `POST /api/flashcards/decks/{deck_id}/export`

#### Request Body

```typescript
interface FlashcardExportRequest {
  format: 'csv_anki' | 'pdf';
  include_hints: boolean;    // Default: true
}
```

#### Supported Formats

| Format | Description | Content-Type |
|--------|-------------|--------------|
| `csv_anki` | Anki-compatible TSV file | `text/tab-separated-values` |
| `pdf` | Printable flashcard sheets | `application/pdf` |

#### Example Request

```typescript
const response = await fetch(`/api/flashcards/decks/${deckId}/export`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    format: "csv_anki",
    include_hints: true
  })
});

// Handle binary response
const blob = await response.blob();
const filename = response.headers.get('Content-Disposition')?.split('filename=')[1]?.replace(/"/g, '');
downloadFile(blob, filename || 'flashcards.txt');
```

#### Response
Binary file download with appropriate `Content-Type` and `Content-Disposition` headers.

---

## TypeScript Interfaces

```typescript
// ============================================================================
// Core Types
// ============================================================================

type FlashcardStatus = 'new' | 'learning' | 'review' | 'mastered';
type CardStyle = 'question_answer' | 'term_definition' | 'cloze' | 'mixed';
type Difficulty = 'easy' | 'medium' | 'hard' | 'mixed';
type GenerationMode = 'standard' | 'enhanced';
type ContentSourceType = 'text' | 'file' | 'url';
type ReviewResult = 'again' | 'hard' | 'good' | 'easy';
type BloomLevel = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate' | 'create';

// ============================================================================
// Request Types
// ============================================================================

interface FlashcardGenerationConfig {
  num_cards?: number | null;
  include_hints: boolean;
  card_style: CardStyle;
  difficulty: Difficulty;
  mode: GenerationMode;
}

interface TextFlashcardRequest {
  content: string;
  title?: string;
  config: FlashcardGenerationConfig;
}

interface FileFlashcardRequest {
  file_id: string;
  title?: string;
  config: FlashcardGenerationConfig;
}

interface UrlFlashcardRequest {
  url: string;
  title?: string;
  config: FlashcardGenerationConfig;
}

interface DeckUpdate {
  title?: string;
  description?: string;
}

interface FlashcardUpdate {
  front?: string;
  back?: string;
  hint?: string;
}

interface StudySessionStart {
  deck_id: string;
  card_limit?: number;
  shuffle: boolean;
  filter_status?: FlashcardStatus[];
}

interface CardReviewResult {
  card_id: string;
  result: ReviewResult;
  time_spent_seconds?: number;
}

interface StudySessionComplete {
  session_id: string;
  results: CardReviewResult[];
}

interface FlashcardExportRequest {
  format: 'csv_anki' | 'pdf';
  include_hints: boolean;
}

// ============================================================================
// Response Types
// ============================================================================

interface Flashcard {
  id: string;
  deck_id: string;
  front: string;
  back: string;
  hint: string | null;
  position: number;
  status: FlashcardStatus;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  next_review: string | null;
  // Enhanced mode fields
  concept_name: string | null;
  bloom_level: BloomLevel | null;
  difficulty_score: number | null;
  source_chunk_id: string | null;
  created_at: string;
  updated_at: string | null;
}

interface Deck {
  id: string;
  created_by: string;
  title: string;
  description: string | null;
  card_count: number;
  content_source_type: ContentSourceType | null;
  content_source_reference: string | null;
  created_at: string;
  updated_at: string | null;
  last_studied: string | null;
}

interface DeckWithCards extends Deck {
  cards: Flashcard[];
}

interface GenerationStats {
  mode: GenerationMode;
  cards_generated: number;
  concepts_extracted?: number;
  chunks_processed?: number;
  cards_per_concept?: number;
  bloom_distribution?: Record<BloomLevel, number>;
}

interface FlashcardGenerationResponse {
  deck_id: string;
  deck_title: string;
  cards: Flashcard[];
  card_count: number;
  content_source_type: ContentSourceType;
  generation_time_ms: number;
  estimated_study_time_minutes: number;
  generation_mode: GenerationMode;
  generation_stats: GenerationStats;
  credits_consumed: number;
}

interface StudySessionResponse {
  session_id: string;
  deck_id: string;
  deck_title: string;
  cards: Flashcard[];
  total_cards: number;
  new_count: number;
  learning_count: number;
  review_count: number;
}

interface StudySessionSummary {
  session_id: string;
  deck_id: string;
  cards_studied: number;
  time_spent_seconds: number;
  accuracy_percent: number;
  cards_mastered: number;
  cards_learning: number;
  streak_days: number;
}

// ============================================================================
// Error Types
// ============================================================================

interface InsufficientCreditsError {
  error: 'insufficient_credits';
  message: string;
  available_credits: number;
  required_credits: number;
  plan: string;
}

interface APIError {
  detail: string | InsufficientCreditsError;
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `200` | Success | Request completed successfully |
| `400` | Bad Request | Invalid input, content too short, invalid URL |
| `401` | Unauthorized | Missing or invalid JWT token |
| `402` | Payment Required | Insufficient credits |
| `403` | Forbidden | Not deck/card owner |
| `404` | Not Found | Deck/card/file not found |
| `422` | Unprocessable Entity | Invalid format, empty deck |
| `429` | Too Many Requests | Rate limited |
| `500` | Server Error | Generation failed, internal error |

### Error Response Examples

#### 400 - Content Too Short
```json
{
  "detail": "Text content must be at least 50 characters"
}
```

#### 402 - Insufficient Credits
```json
{
  "detail": {
    "error": "insufficient_credits",
    "message": "Not enough credits for enhanced flashcard generation.",
    "available_credits": 1,
    "required_credits": 2,
    "plan": "free"
  }
}
```

#### 404 - Not Found
```json
{
  "detail": "Deck not found"
}
```

#### 500 - Generation Failed
```json
{
  "detail": "Failed to generate flashcards: LLM response parsing error"
}
```

### Frontend Error Handling Pattern

```typescript
async function generateFlashcards(request: TextFlashcardRequest): Promise<FlashcardGenerationResponse> {
  try {
    const response = await fetch('/api/flashcards/generate/text', {
      method: 'POST',
      headers,
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      const error = await response.json();
      
      switch (response.status) {
        case 402:
          // Insufficient credits - show upgrade modal
          const creditError = error.detail as InsufficientCreditsError;
          showUpgradeModal({
            available: creditError.available_credits,
            required: creditError.required_credits,
            plan: creditError.plan
          });
          throw new InsufficientCreditsException(creditError);
          
        case 400:
          // Validation error - show user message
          toast.error(error.detail);
          throw new ValidationException(error.detail);
          
        case 429:
          // Rate limited - show retry message
          toast.error('Too many requests. Please wait a moment.');
          throw new RateLimitException();
          
        default:
          // Generic error
          toast.error('Failed to generate flashcards. Please try again.');
          throw new APIException(error.detail);
      }
    }

    return await response.json();
  } catch (error) {
    if (error instanceof TypeError) {
      // Network error
      toast.error('Network error. Please check your connection.');
    }
    throw error;
  }
}
```

---

## Generation Modes Explained

### Standard Mode (1 Credit)

**Pipeline**: Content → LLM → Flashcards

- Direct LLM prompt with content
- Faster generation (5-15 seconds)
- Good for straightforward content
- Basic quality flashcards

**Best For**:
- Quick study sessions
- Simple factual content
- Time-sensitive situations

### Enhanced Mode (2 Credits)

**Pipeline**: Content → RAG Ingestion → Concept Extraction → Context Retrieval → LLM → Flashcards

1. **RAG Ingestion**: Content is chunked and embedded
2. **Concept Extraction**: AI identifies key concepts/topics
3. **Context Retrieval**: Relevant chunks are retrieved per concept
4. **Generation**: Cards generated with full context and Bloom's taxonomy

**Enhanced Features**:
- `concept_name`: The concept each card tests
- `bloom_level`: Bloom's taxonomy level (remember, understand, apply, analyze, evaluate, create)
- `difficulty_score`: 0.0-1.0 difficulty rating
- `source_chunk_id`: Traceability to source content

**Best For**:
- Exam preparation
- Deep learning
- Complex technical content
- When accuracy is critical

### UI Toggle Implementation

```tsx
const [mode, setMode] = useState<GenerationMode>('standard');

<div className="flex gap-4">
  <button
    onClick={() => setMode('standard')}
    className={`px-4 py-2 rounded ${mode === 'standard' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}
  >
    ⚡ Standard (1 credit)
    <span className="text-xs block">Fast & Good</span>
  </button>
  
  <button
    onClick={() => setMode('enhanced')}
    className={`px-4 py-2 rounded ${mode === 'enhanced' ? 'bg-purple-500 text-white' : 'bg-gray-200'}`}
  >
    🧠 Enhanced (2 credits)
    <span className="text-xs block">RAG + Bloom's Taxonomy</span>
  </button>
</div>
```

---

## UI Implementation Guide

### Recommended UI Components

#### 1. Flashcard Generation Form

```tsx
interface FlashcardGeneratorProps {
  onGenerated: (response: FlashcardGenerationResponse) => void;
}

function FlashcardGenerator({ onGenerated }: FlashcardGeneratorProps) {
  const [source, setSource] = useState<'text' | 'file' | 'url'>('text');
  const [content, setContent] = useState('');
  const [fileId, setFileId] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [config, setConfig] = useState<FlashcardGenerationConfig>({
    num_cards: null,  // Auto-calculate
    include_hints: true,
    card_style: 'mixed',
    difficulty: 'mixed',
    mode: 'standard'
  });
  const [isGenerating, setIsGenerating] = useState(false);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      let response: FlashcardGenerationResponse;
      
      switch (source) {
        case 'text':
          response = await generateFromText({ content, title, config });
          break;
        case 'file':
          if (!fileId) throw new Error('No file selected');
          response = await generateFromFile({ file_id: fileId, title, config });
          break;
        case 'url':
          response = await generateFromUrl({ url, title, config });
          break;
      }
      
      onGenerated(response);
      toast.success(`Generated ${response.card_count} flashcards!`);
    } catch (error) {
      // Error handling shown in earlier section
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); handleGenerate(); }}>
      {/* Source selector tabs */}
      {/* Content input (textarea/file upload/URL input) */}
      {/* Configuration options */}
      {/* Mode toggle */}
      {/* Generate button with loading state */}
    </form>
  );
}
```

#### 2. Flashcard Study Component

```tsx
interface FlashcardStudyProps {
  session: StudySessionResponse;
  onComplete: (summary: StudySessionSummary) => void;
}

function FlashcardStudy({ session, onComplete }: FlashcardStudyProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [results, setResults] = useState<CardReviewResult[]>([]);
  const [startTime, setStartTime] = useState(Date.now());

  const currentCard = session.cards[currentIndex];
  const isLastCard = currentIndex === session.cards.length - 1;

  const handleResult = async (result: ReviewResult) => {
    const timeSpent = Math.round((Date.now() - startTime) / 1000);
    
    const newResult: CardReviewResult = {
      card_id: currentCard.id,
      result,
      time_spent_seconds: timeSpent
    };
    
    const updatedResults = [...results, newResult];
    setResults(updatedResults);

    if (isLastCard) {
      // Complete session
      const summary = await completeStudySession({
        session_id: session.session_id,
        results: updatedResults
      });
      onComplete(summary);
    } else {
      // Next card
      setCurrentIndex(currentIndex + 1);
      setIsFlipped(false);
      setShowHint(false);
      setStartTime(Date.now());
    }
  };

  return (
    <div className="study-container">
      {/* Progress bar */}
      <div className="progress-bar">
        {currentIndex + 1} / {session.total_cards}
      </div>

      {/* Flashcard */}
      <div 
        className={`flashcard ${isFlipped ? 'flipped' : ''}`}
        onClick={() => setIsFlipped(!isFlipped)}
      >
        <div className="front">
          <p>{currentCard.front}</p>
          {currentCard.hint && !isFlipped && (
            <button onClick={(e) => { e.stopPropagation(); setShowHint(true); }}>
              Show Hint
            </button>
          )}
          {showHint && <p className="hint">💡 {currentCard.hint}</p>}
        </div>
        <div className="back">
          <p>{currentCard.back}</p>
        </div>
      </div>

      {/* Answer buttons (only show when flipped) */}
      {isFlipped && (
        <div className="answer-buttons">
          <button onClick={() => handleResult('again')} className="btn-again">
            Again
          </button>
          <button onClick={() => handleResult('hard')} className="btn-hard">
            Hard
          </button>
          <button onClick={() => handleResult('good')} className="btn-good">
            Good
          </button>
          <button onClick={() => handleResult('easy')} className="btn-easy">
            Easy
          </button>
        </div>
      )}
    </div>
  );
}
```

#### 3. Deck List Component

```tsx
function DeckList() {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDecks();
  }, []);

  const fetchDecks = async () => {
    const response = await fetch('/api/flashcards/decks', { headers });
    setDecks(await response.json());
    setLoading(false);
  };

  const handleDelete = async (deckId: string) => {
    if (!confirm('Delete this deck and all its cards?')) return;
    
    await fetch(`/api/flashcards/decks/${deckId}`, {
      method: 'DELETE',
      headers
    });
    
    setDecks(decks.filter(d => d.id !== deckId));
    toast.success('Deck deleted');
  };

  return (
    <div className="deck-list">
      {decks.map(deck => (
        <div key={deck.id} className="deck-card">
          <h3>{deck.title}</h3>
          <p>{deck.card_count} cards</p>
          <p>Last studied: {deck.last_studied ? formatDate(deck.last_studied) : 'Never'}</p>
          
          <div className="actions">
            <Link href={`/flashcards/${deck.id}/study`}>
              <button>Study</button>
            </Link>
            <Link href={`/flashcards/${deck.id}`}>
              <button>View</button>
            </Link>
            <button onClick={() => handleDelete(deck.id)}>Delete</button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

#### 4. Session Summary Component

```tsx
function StudySessionSummaryView({ summary }: { summary: StudySessionSummary }) {
  return (
    <div className="session-summary">
      <h2>🎉 Session Complete!</h2>
      
      <div className="stats-grid">
        <div className="stat">
          <span className="value">{summary.cards_studied}</span>
          <span className="label">Cards Studied</span>
        </div>
        
        <div className="stat">
          <span className="value">{Math.round(summary.time_spent_seconds / 60)}m</span>
          <span className="label">Time Spent</span>
        </div>
        
        <div className="stat">
          <span className="value">{summary.accuracy_percent}%</span>
          <span className="label">Accuracy</span>
        </div>
        
        <div className="stat">
          <span className="value">{summary.cards_mastered}</span>
          <span className="label">Mastered</span>
        </div>
      </div>
      
      <div className="actions">
        <button onClick={() => window.location.reload()}>Study Again</button>
        <Link href="/flashcards">
          <button>Back to Decks</button>
        </Link>
      </div>
    </div>
  );
}
```

---

## Example Flows

### Flow 1: Generate and Study Flashcards

```typescript
// 1. Check credits first
const billing = await getBillingState();
const mode = billing.available_credits >= 2 ? 'enhanced' : 'standard';

// 2. Generate flashcards
const generationResponse = await generateFromText({
  content: userInputContent,
  title: "My Study Set",
  config: {
    num_cards: 15,
    include_hints: true,
    card_style: 'mixed',
    difficulty: 'mixed',
    mode
  }
});

// 3. Navigate to study view
router.push(`/flashcards/${generationResponse.deck_id}/study`);

// 4. Start study session
const session = await startStudySession({
  deck_id: generationResponse.deck_id,
  shuffle: true,
  filter_status: ['new', 'learning', 'review']
});

// 5. User studies cards...

// 6. Complete session
const summary = await completeStudySession({
  session_id: session.session_id,
  results: collectedResults
});

// 7. Show summary
displaySummary(summary);
```

### Flow 2: Export to Anki

```typescript
// 1. User selects deck to export
const deckId = selectedDeck.id;

// 2. Show export options
const format = await showExportDialog(); // 'csv_anki' or 'pdf'

// 3. Export
const response = await fetch(`/api/flashcards/decks/${deckId}/export`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    format: 'csv_anki',
    include_hints: true
  })
});

// 4. Download file
const blob = await response.blob();
const filename = `${selectedDeck.title}_anki.txt`;
downloadBlob(blob, filename);

// 5. Show instructions
showAnkiImportInstructions();
```

### Flow 3: Edit AI-Generated Card

```typescript
// 1. User finds card with error
const cardToEdit = deck.cards.find(c => c.id === selectedCardId);

// 2. Show edit modal
const updates = await showEditCardModal(cardToEdit);

// 3. Save changes
const updatedCard = await fetch(`/api/flashcards/cards/${cardToEdit.id}`, {
  method: 'PATCH',
  headers,
  body: JSON.stringify({
    front: updates.front,
    back: updates.back,
    hint: updates.hint
  })
});

// 4. Update local state
setDeck(prev => ({
  ...prev,
  cards: prev.cards.map(c => c.id === cardToEdit.id ? updatedCard : c)
}));

toast.success('Card updated');
```

---

## Appendix: API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/flashcards/generate/text` | Generate from text content |
| `POST` | `/api/flashcards/generate/file` | Generate from uploaded file |
| `POST` | `/api/flashcards/generate/url` | Generate from URL |
| `GET` | `/api/flashcards/decks` | List user's decks |
| `GET` | `/api/flashcards/decks/{deck_id}` | Get deck with cards |
| `PATCH` | `/api/flashcards/decks/{deck_id}` | Update deck |
| `DELETE` | `/api/flashcards/decks/{deck_id}` | Delete deck |
| `PATCH` | `/api/flashcards/cards/{card_id}` | Update card |
| `DELETE` | `/api/flashcards/cards/{card_id}` | Delete card |
| `POST` | `/api/flashcards/study/start` | Start study session |
| `POST` | `/api/flashcards/study/complete` | Complete study session |
| `POST` | `/api/flashcards/decks/{deck_id}/export` | Export deck |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-25 | Initial release with standard/enhanced modes, full CRUD, study sessions, and exports |
