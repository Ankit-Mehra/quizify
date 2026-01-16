# Frontend Integration Guide: Quiz & Flashcard Generation API

> **Last Updated:** January 2026  
> **API Version:** v2.0 (Breaking Changes)

## Overview

This document describes the unified API structure for quiz and flashcard generation. Both features now follow the same consistent patterns for all content sources.

---

## API Endpoint Structure

### Quiz Generation Endpoints

| Endpoint | Method | Content-Type | Description |
|----------|--------|--------------|-------------|
| `/api/quiz/generate/text` | POST | `application/json` | Generate from text input |
| `/api/quiz/generate/upload` | POST | `multipart/form-data` | Generate from new file upload |
| `/api/quiz/generate/file/{file_id}` | POST | `application/json` | Generate from existing file (UUID) |
| `/api/quiz/generate/url` | POST | `application/json` | Generate from web URL |

### Flashcard Generation Endpoints

| Endpoint | Method | Content-Type | Description |
|----------|--------|--------------|-------------|
| `/api/flashcards/generate/text` | POST | `application/json` | Generate from text input |
| `/api/flashcards/generate/upload` | POST | `multipart/form-data` | Generate from new file upload |
| `/api/flashcards/generate/file/{file_id}` | POST | `application/json` | Generate from existing file (UUID) |
| `/api/flashcards/generate/url` | POST | `application/json` | Generate from web URL |

### File Management Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/files/upload` | POST | Upload file for later use (returns UUID) |
| `/api/files` | GET | List user's uploaded files |
| `/api/files/{file_id}` | DELETE | Delete a file |

---

## Generation Flows

### Flow 1: Direct File Upload (Single Request)

Use this when the user uploads a file and immediately wants to generate quiz/flashcards.

```
┌─────────────────────────────────────────────────────────────┐
│ User uploads file + clicks "Generate"                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend: POST /api/quiz/generate/upload                    │
│           OR POST /api/flashcards/generate/upload           │
│                                                             │
│ Content-Type: multipart/form-data                           │
│ Body: file + form fields                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend:                                                    │
│   1. Validates file (size, type)                            │
│   2. Extracts text content                                  │
│   3. Saves file to storage → generates UUID                 │
│   4. Generates quiz/flashcards                              │
│   5. Returns result + file_id                               │
│                                                             │
│ On failure: Cleans up file, refunds credits                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Response: Quiz/Flashcard data + file_id (UUID)              │
│ Store file_id for future regeneration                       │
└─────────────────────────────────────────────────────────────┘
```

### Flow 2: Existing File (Two Requests)

Use this when the user selects a previously uploaded file.

```
┌─────────────────────────────────────────────────────────────┐
│ User selects existing file from file picker                 │
│ (File was uploaded earlier via /api/files/upload)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend: POST /api/quiz/generate/file/{file_id}            │
│           OR POST /api/flashcards/generate/file/{file_id}   │
│                                                             │
│ Content-Type: application/json                              │
│ URL: file_id is the UUID in the path                        │
│ Body: JSON with generation options                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend:                                                    │
│   1. Fetches file from storage using UUID                   │
│   2. Extracts text content                                  │
│   3. Generates quiz/flashcards                              │
│   4. Returns result                                         │
└─────────────────────────────────────────────────────────────┘
```

### Flow 3: Standalone File Upload (For Later Use)

Use this for the dedicated "Upload Files" page where users manage their files.

```
┌─────────────────────────────────────────────────────────────┐
│ User uploads file on "My Files" page                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend: POST /api/files/upload                            │
│ Content-Type: multipart/form-data                           │
│ Body: file only                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Response:                                                   │
│ {                                                           │
│   "message": "File uploaded successfully",                  │
│   "file_id": "550e8400-e29b-41d4-a716-446655440000",       │
│   "filename": "my-document.pdf"                             │
│ }                                                           │
│                                                             │
│ ⚠️ IMPORTANT: Store file_id (UUID), not filename!          │
└─────────────────────────────────────────────────────────────┘
```

---

## Request/Response Examples

### 1. Quiz from Direct File Upload

**Request:**
```javascript
const formData = new FormData();
formData.append('file', fileObject);
formData.append('title', 'My Quiz Title');
formData.append('num_questions', '10');
formData.append('question_type', 'mixed');
formData.append('mode', 'standard'); // or 'enhanced'

const response = await fetch('/api/quiz/generate/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});
```

**Response:**
```json
{
  "quiz_id": "uuid-here",
  "title": "My Quiz Title",
  "questions": [...],
  "message": "Quiz generated successfully from file (standard mode)",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "generation_time_ms": 2500,
  "mode": "standard"
}
```

### 2. Quiz from Existing File

**Request:**
```javascript
const fileId = '550e8400-e29b-41d4-a716-446655440000'; // UUID from previous upload

const response = await fetch(`/api/quiz/generate/file/${fileId}`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: 'My Quiz Title',
    num_questions: 10,
    question_type: ['mixed'],
    mode: 'standard'
  })
});
```

### 3. Flashcard from Direct File Upload

**Request:**
```javascript
const formData = new FormData();
formData.append('file', fileObject);
formData.append('title', 'My Flashcard Deck');
formData.append('card_count', '15');
formData.append('card_style', 'mixed');     // 'simple', 'detailed', 'mixed'
formData.append('difficulty', 'intermediate'); // 'beginner', 'intermediate', 'advanced'
formData.append('include_hints', 'true');
formData.append('mode', 'standard');        // or 'enhanced'

const response = await fetch('/api/flashcards/generate/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});
```

**Response:**
```json
{
  "deck_id": "uuid-here",
  "title": "My Flashcard Deck",
  "cards": [
    {
      "id": "card-uuid",
      "front": "What is...?",
      "back": "The answer is...",
      "hint": "Think about..."
    }
  ],
  "card_count": 15,
  "generation_time_ms": 1800,
  "credits_consumed": 0.5,
  "generation_mode": "standard"
}
```

### 4. Flashcard from Existing File

**Request:**
```javascript
const fileId = '550e8400-e29b-41d4-a716-446655440000';

const response = await fetch(`/api/flashcards/generate/file/${fileId}`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: 'My Flashcard Deck',
    config: {
      card_count: 15,
      card_style: 'mixed',
      difficulty: 'intermediate',
      include_hints: true,
      mode: 'standard'
    }
  })
});
```

### 5. Text Input Generation

**Quiz from Text:**
```javascript
const response = await fetch('/api/quiz/generate/text', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: 'My Quiz',
    content: 'Your text content here...',
    num_questions: 10,
    question_type: ['mixed'],
    mode: 'standard'
  })
});
```

**Flashcards from Text:**
```javascript
const response = await fetch('/api/flashcards/generate/text', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    content: 'Your text content here...',
    title: 'My Deck',
    config: {
      card_count: 10,
      card_style: 'mixed',
      difficulty: 'intermediate',
      include_hints: true,
      mode: 'standard'
    }
  })
});
```

### 6. URL Generation

**Quiz from URL:**
```javascript
const response = await fetch('/api/quiz/generate/url', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    title: 'Web Content Quiz',
    url: 'https://example.com/article',
    num_questions: 10,
    question_type: ['mixed'],
    mode: 'standard'
  })
});
```

**Flashcards from URL:**
```javascript
const response = await fetch('/api/flashcards/generate/url', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    url: 'https://example.com/article',
    title: 'Web Content Flashcards',
    config: {
      card_count: 15,
      card_style: 'mixed',
      difficulty: 'intermediate',
      include_hints: true,
      mode: 'standard'
    }
  })
});
```

---

## Generation Modes

| Mode | Credits | Speed | Quality | Use Case |
|------|---------|-------|---------|----------|
| `standard` | 0.5 (flashcard) / 1 (quiz) | Fast (~2-5s) | Good | Quick generation |
| `enhanced` | 1.0 (flashcard) / 2 (quiz) | Slower (~5-15s) | Premium | Better quality, Bloom's taxonomy |

---

## File Handling Best Practices

### ✅ DO:

1. **Store file_id (UUID)** when displaying file list:
   ```javascript
   // Correct - use the UUID for API calls
   const files = await fetchFiles();
   files.forEach(file => {
     fileList.push({
       id: file.id,           // UUID: "550e8400-e29b-41d4-a716-446655440000"
       displayName: file.original_filename  // "my-document.pdf"
     });
   });
   ```

2. **Use UUID in API calls:**
   ```javascript
   // Correct
   await fetch(`/api/quiz/generate/file/${file.id}`, ...);
   ```

3. **Handle both new upload and existing file:**
   ```javascript
   async function generateQuiz(file, existingFileId, options) {
     if (existingFileId) {
       // Use existing file endpoint
       return fetch(`/api/quiz/generate/file/${existingFileId}`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json', ... },
         body: JSON.stringify(options)
       });
     } else {
       // Use upload endpoint
       const formData = new FormData();
       formData.append('file', file);
       Object.entries(options).forEach(([key, value]) => {
         formData.append(key, value);
       });
       return fetch('/api/quiz/generate/upload', {
         method: 'POST',
         body: formData
       });
     }
   }
   ```

### ❌ DON'T:

1. **Don't use filename as identifier:**
   ```javascript
   // WRONG - This will fail!
   await fetch(`/api/quiz/generate/file/${file.filename}`, ...);
   // Error: "my-document.pdf" is not a valid UUID
   ```

2. **Don't mix up endpoint paths:**
   ```javascript
   // WRONG - /upload expects multipart, not JSON
   await fetch('/api/quiz/generate/upload', {
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ file_id: '...' })
   });
   ```

---

## Error Handling

### Common Error Responses

| Status | Error | Cause | Solution |
|--------|-------|-------|----------|
| 400 | Invalid file type | Wrong file format | Accept only PDF, DOCX, TXT |
| 402 | Insufficient credits | User out of credits | Prompt user to upgrade |
| 404 | File not found | Invalid file_id | Re-fetch file list, verify UUID |
| 413 | File too large | File > 10MB | Show file size limit message |
| 500 | Internal error | Server issue | Retry with exponential backoff |

### Error Response Format

```json
{
  "detail": {
    "error": "insufficient_credits",
    "message": "Not enough credits for enhanced flashcard generation.",
    "available_credits": 0.5,
    "required_credits": 1.0,
    "plan": "free"
  }
}
```

---

## File List API

### Get User Files

```javascript
const response = await fetch('/api/files', {
  headers: { 'Authorization': `Bearer ${accessToken}` }
});

const data = await response.json();
// data.files = [
//   {
//     "id": "550e8400-e29b-41d4-a716-446655440000",  // UUID - use this!
//     "original_filename": "my-document.pdf",        // Display name
//     "file_type": "application/pdf",
//     "file_size_bytes": 1048576,
//     "uploaded_at": "2026-01-15T10:30:00Z"
//   }
// ]
```

---

## Migration from Old API

If you were using the old endpoints, here's the mapping:

| Old Endpoint | New Endpoint |
|--------------|--------------|
| `POST /api/quiz/generate/file` (multipart) | `POST /api/quiz/generate/upload` |
| `POST /api/quiz/generate/{file_id}` | `POST /api/quiz/generate/file/{file_id}` |
| `POST /api/flashcards/generate/file` (JSON with file_id in body) | `POST /api/flashcards/generate/file/{file_id}` (file_id in URL) |
| `POST /api/flashcards/generate/file-upload` | `POST /api/flashcards/generate/upload` |

---

## Quick Reference

### Endpoint Decision Tree

```
User wants to generate quiz/flashcards
          │
          ▼
    ┌─────────────┐
    │ Content     │
    │ Source?     │
    └─────────────┘
          │
    ┌─────┴─────┬──────────┬──────────┐
    ▼           ▼          ▼          ▼
  Text      New File   Existing    URL
    │           │       File        │
    ▼           ▼          │        ▼
/generate   /generate      │    /generate
  /text      /upload       │      /url
                           ▼
                    /generate/file/{uuid}
```

### Content-Type Quick Reference

| Endpoint Pattern | Content-Type |
|------------------|--------------|
| `/generate/upload` | `multipart/form-data` |
| `/generate/text` | `application/json` |
| `/generate/file/{id}` | `application/json` |
| `/generate/url` | `application/json` |

---

## Support

For questions or issues:
- Check error response `detail` field for specific error codes
- Verify file_id is a valid UUID format
- Ensure correct Content-Type header for each endpoint
