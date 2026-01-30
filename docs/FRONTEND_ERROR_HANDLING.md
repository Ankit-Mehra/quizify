# Frontend Error Handling Guide

## Error Response Format

All Quizify API errors follow a consistent JSON structure:

```json
{
  "detail": "Human-readable error message"
}
```

### Parsing Errors

```typescript
// ✅ CORRECT - Extract the detail field
const response = await fetch('/api/endpoint', options);
if (!response.ok) {
  const errorData = await response.json();
  const message = errorData.detail;  // "Insufficient content in file..."
  throw new Error(message);
}

// ❌ WRONG - Displaying raw JSON
showError(JSON.stringify(errorData));  // Shows: {"detail":"..."}
```

---

## Error Types by Status Code

| Status | Type | `detail` Format | Example |
|--------|------|-----------------|---------|
| 400 | Bad Request | `string` | `"Insufficient content in file. Please provide a document with at least 50 characters of text."` |
| 401 | Unauthorized | `string` | `"Authentication required"` or `"Invalid or expired token"` |
| 403 | Forbidden | `string` | `"Permission denied. You can only submit your own quiz answers."` |
| 404 | Not Found | `string` | `"Quiz not found"` or `"File not found"` |
| 409 | Conflict | `string` | `"This submission already exists."` |
| 422 | Validation Error | `object` | See below |
| 429 | Rate Limited | `string` | `"Quota exceeded"` |
| 500 | Server Error | `string` | `"An internal error occurred. Please try again later."` |
| 503 | Service Unavailable | `string` | `"Session management service temporarily unavailable."` |

---

## 422 Validation Error (Special Case)

Request validation errors return an additional `errors` array:

```json
{
  "detail": "Request validation failed",
  "errors": [
    { "location": "body -> num_questions", "message": "ensure this value is greater than 0" },
    { "location": "body -> title", "message": "field required" }
  ]
}
```

### Handling 422 Errors

```typescript
if (response.status === 422) {
  const errorData = await response.json();
  
  // Option 1: Show summary message
  showError(errorData.detail);  // "Request validation failed"
  
  // Option 2: Show field-specific errors
  if (errorData.errors) {
    errorData.errors.forEach(err => {
      showFieldError(err.location, err.message);
    });
  }
}
```

---

## Recommended Error Handler

```typescript
interface ApiError {
  detail: string;
  errors?: Array<{ location: string; message: string }>;
}

async function handleApiError(response: Response): Promise<never> {
  let message = 'An unexpected error occurred';
  
  try {
    const data: ApiError = await response.json();
    message = data.detail || message;
    
    // For validation errors, append field details
    if (response.status === 422 && data.errors?.length) {
      const fieldErrors = data.errors.map(e => e.message).join(', ');
      message = `${data.detail}: ${fieldErrors}`;
    }
  } catch {
    // Response wasn't JSON
    message = response.statusText || message;
  }
  
  throw new Error(message);
}

// Usage
const response = await fetch('/api/quiz/generate-from-file', options);
if (!response.ok) {
  await handleApiError(response);
}
```

---

## Common Error Messages (Reference)

### Quiz Generation
| Error | Meaning |
|-------|---------|
| `"Insufficient content in file. Please provide a document with at least 50 characters of text."` | Uploaded file has too little text |
| `"Unsupported file type"` | File format not PDF/DOCX/TXT |
| `"File size exceeds 10MB limit"` | File too large |
| `"Quota exceeded"` | User hit quiz generation limit |

### Authentication
| Error | Meaning |
|-------|---------|
| `"Authentication required"` | No token provided |
| `"Invalid or expired token"` | Token expired or malformed |
| `"Session expired or invalid"` | Redis session expired |

### Submissions
| Error | Meaning |
|-------|---------|
| `"Quiz not found"` | Quiz ID doesn't exist |
| `"Permission denied"` | User doesn't own the quiz |
| `"This submission already exists"` | Duplicate submission attempt |
