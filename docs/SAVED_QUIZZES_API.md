# Saved Quizzes API - Filtering & Pagination

## Overview

The `GET /api/quiz/my-quizzes` endpoint now supports comprehensive filtering and pagination to power the Saved Quizzes page efficiently at scale.

## Endpoint

```
GET /api/quiz/my-quizzes
```

**Authentication Required:** Yes (Bearer token)

---

## Query Parameters

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `title` | string | - | No | Case-insensitive partial match search |
| `start_date` | date | - | No | Filter quizzes created on or after (YYYY-MM-DD) |
| `end_date` | date | - | No | Filter quizzes created on or before (YYYY-MM-DD) |
| `source_type` | string | - | No | Filter by content source: `file`, `url`, `text` |
| `mode` | string | - | No | Filter by generation mode: `standard`, `enhanced` |
| `page` | integer | 1 | No | Page number (1-indexed) |
| `limit` | integer | 20 | No | Items per page (1-100) |

---

## Response Schema

```typescript
interface PaginatedQuizzesResponse {
  quizzes: Quiz[];
  total: number;        // Total matching quizzes
  page: number;         // Current page
  limit: number;        // Items per page
  total_pages: number;  // Total pages available
  has_next: boolean;    // More pages after current?
  has_previous: boolean; // Pages before current?
}

interface Quiz {
  id: string;
  title: string;
  created_by: string;
  created_at: string;           // ISO 8601 datetime
  generation_mode: string;      // "standard" | "enhanced"
  content_source_type: string;  // "file" | "url" | "text"
  question_count: number;
}
```

---

## Example Requests

### Basic - Get First Page (Default)
```bash
GET /api/quiz/my-quizzes
```

### Search by Title
```bash
GET /api/quiz/my-quizzes?title=Python
```

### Filter by Source Type
```bash
# Only file-based quizzes
GET /api/quiz/my-quizzes?source_type=file

# Only URL-based quizzes
GET /api/quiz/my-quizzes?source_type=url

# Only text-based quizzes
GET /api/quiz/my-quizzes?source_type=text
```

### Filter by Generation Mode
```bash
# Only enhanced (RAG) quizzes
GET /api/quiz/my-quizzes?mode=enhanced

# Only standard quizzes
GET /api/quiz/my-quizzes?mode=standard
```

### Filter by Date Range
```bash
# Quizzes from December 2025
GET /api/quiz/my-quizzes?start_date=2025-12-01&end_date=2025-12-31

# Quizzes since last week
GET /api/quiz/my-quizzes?start_date=2025-11-27
```

### Pagination
```bash
# Page 2 with 10 items per page
GET /api/quiz/my-quizzes?page=2&limit=10

# First 50 results
GET /api/quiz/my-quizzes?limit=50
```

### Combined Filters
```bash
# Enhanced file quizzes from December, page 2
GET /api/quiz/my-quizzes?source_type=file&mode=enhanced&start_date=2025-12-01&page=2&limit=15
```

---

## Example Response

```json
{
  "quizzes": [
    {
      "id": "dda7e3f7-1344-4e75-a304-e3e73d7579ac",
      "title": "Machine Learning Fundamentals",
      "created_by": "760602fe-b19f-472a-b65e-060f9e195529",
      "created_at": "2025-12-04T21:52:37.278384+00:00",
      "generation_mode": "enhanced",
      "content_source_type": "file",
      "question_count": 12
    },
    {
      "id": "1d2126ea-da9b-482b-8d4e-362fa8bee52e",
      "title": "Python Basics Quiz",
      "created_by": "760602fe-b19f-472a-b65e-060f9e195529",
      "created_at": "2025-12-03T15:30:00.000000+00:00",
      "generation_mode": "standard",
      "content_source_type": "text",
      "question_count": 10
    }
  ],
  "total": 47,
  "page": 1,
  "limit": 20,
  "total_pages": 3,
  "has_next": true,
  "has_previous": false
}
```

---

## Frontend Integration Guide

### React/Next.js Example

```tsx
// types.ts
interface Quiz {
  id: string;
  title: string;
  created_at: string;
  generation_mode: 'standard' | 'enhanced';
  content_source_type: 'file' | 'url' | 'text';
  question_count: number;
}

interface PaginatedResponse {
  quizzes: Quiz[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

interface QuizFilters {
  title?: string;
  source_type?: 'file' | 'url' | 'text';
  mode?: 'standard' | 'enhanced';
  start_date?: string;
  end_date?: string;
  page: number;
  limit: number;
}
```

```tsx
// hooks/useQuizzes.ts
import { useState, useEffect } from 'react';

export function useQuizzes(filters: QuizFilters) {
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuizzes = async () => {
      setLoading(true);
      try {
        // Build query string from filters
        const params = new URLSearchParams();
        
        if (filters.title) params.set('title', filters.title);
        if (filters.source_type) params.set('source_type', filters.source_type);
        if (filters.mode) params.set('mode', filters.mode);
        if (filters.start_date) params.set('start_date', filters.start_date);
        if (filters.end_date) params.set('end_date', filters.end_date);
        params.set('page', filters.page.toString());
        params.set('limit', filters.limit.toString());

        const response = await fetch(
          `/api/quiz/my-quizzes?${params.toString()}`,
          {
            headers: {
              'Authorization': `Bearer ${getToken()}`,
            },
          }
        );

        if (!response.ok) throw new Error('Failed to fetch quizzes');
        
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchQuizzes();
  }, [filters]);

  return { data, loading, error };
}
```

```tsx
// components/SavedQuizzes.tsx
import { useState } from 'react';
import { useQuizzes } from '@/hooks/useQuizzes';

export function SavedQuizzes() {
  const [filters, setFilters] = useState<QuizFilters>({
    page: 1,
    limit: 20,
  });

  const { data, loading, error } = useQuizzes(filters);

  // Debounced search handler
  const handleSearch = useDebouncedCallback((value: string) => {
    setFilters(prev => ({ ...prev, title: value || undefined, page: 1 }));
  }, 300);

  const handleSourceFilter = (source: string | null) => {
    setFilters(prev => ({
      ...prev,
      source_type: source as 'file' | 'url' | 'text' | undefined,
      page: 1,
    }));
  };

  const handleModeFilter = (mode: string | null) => {
    setFilters(prev => ({
      ...prev,
      mode: mode as 'standard' | 'enhanced' | undefined,
      page: 1,
    }));
  };

  const handleDateRange = (start: string | null, end: string | null) => {
    setFilters(prev => ({
      ...prev,
      start_date: start || undefined,
      end_date: end || undefined,
      page: 1,
    }));
  };

  const handlePageChange = (newPage: number) => {
    setFilters(prev => ({ ...prev, page: newPage }));
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error} />;
  if (!data) return null;

  return (
    <div className="saved-quizzes">
      {/* Filter Controls */}
      <div className="filters">
        <SearchInput
          placeholder="Search quizzes..."
          onChange={handleSearch}
        />
        
        <Select
          placeholder="All Sources"
          options={[
            { value: '', label: 'All Sources' },
            { value: 'file', label: 'PDF/Doc' },
            { value: 'url', label: 'URL' },
            { value: 'text', label: 'Text' },
          ]}
          onChange={handleSourceFilter}
        />
        
        <DateRangePicker
          onChange={(start, end) => handleDateRange(start, end)}
        />
        
        <Select
          placeholder="All Modes"
          options={[
            { value: '', label: 'All Modes' },
            { value: 'enhanced', label: 'Enhanced' },
            { value: 'standard', label: 'Standard' },
          ]}
          onChange={handleModeFilter}
        />
      </div>

      {/* Quiz List */}
      <QuizTable quizzes={data.quizzes} />

      {/* Pagination */}
      <Pagination
        currentPage={data.page}
        totalPages={data.total_pages}
        hasNext={data.has_next}
        hasPrevious={data.has_previous}
        onPageChange={handlePageChange}
      />
      
      <div className="pagination-info">
        Showing {data.quizzes.length} of {data.total} quizzes
        (Page {data.page} of {data.total_pages})
      </div>
    </div>
  );
}
```

```tsx
// components/Pagination.tsx
interface PaginationProps {
  currentPage: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
  onPageChange: (page: number) => void;
}

export function Pagination({
  currentPage,
  totalPages,
  hasNext,
  hasPrevious,
  onPageChange,
}: PaginationProps) {
  return (
    <div className="pagination">
      <button
        disabled={!hasPrevious}
        onClick={() => onPageChange(currentPage - 1)}
      >
        Previous
      </button>
      
      <span>Page {currentPage} of {totalPages}</span>
      
      <button
        disabled={!hasNext}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Next
      </button>
    </div>
  );
}
```

---

## Error Responses

### Invalid Date Range (400)
```json
{
  "detail": "start_date must be less than or equal to end_date"
}
```

### Invalid Source Type (400)
```json
{
  "detail": "source_type must be one of: file, url, text"
}
```

### Invalid Mode (400)
```json
{
  "detail": "mode must be one of: standard, enhanced"
}
```

### Unauthorized (401)
```json
{
  "detail": "Not authenticated"
}
```

---

## Performance Notes

1. **Database Indexes**: The backend uses optimized indexes for:
   - `idx_quizzes_title_trgm` - Trigram index for fast ILIKE title search
   - `idx_quizzes_user_created_at` - Composite index for user + date filtering

2. **Single Query Design**: Uses Supabase embedded counts to avoid N+1 queries

3. **Pagination**: Always use pagination for production - avoid loading all quizzes at once

4. **Recommended Limits**:
   - Default: 20 items per page
   - Maximum: 100 items per page
   - For mobile: Consider 10 items per page

---

## Migration from Old API

If your frontend was previously expecting a simple array response:

**Before (Old Response):**
```json
[
  { "id": "...", "title": "Quiz 1", ... },
  { "id": "...", "title": "Quiz 2", ... }
]
```

**After (New Response):**
```json
{
  "quizzes": [
    { "id": "...", "title": "Quiz 1", ... },
    { "id": "...", "title": "Quiz 2", ... }
  ],
  "total": 2,
  "page": 1,
  "limit": 20,
  "total_pages": 1,
  "has_next": false,
  "has_previous": false
}
```

**Migration Code:**
```typescript
// Old code
const quizzes = await fetchQuizzes();
renderQuizList(quizzes);

// New code
const response = await fetchQuizzes();
renderQuizList(response.quizzes);
renderPagination(response);
```

---

## UI Mapping

| UI Element | API Parameter | Values |
|------------|---------------|--------|
| Search input | `title` | Any string |
| "All Sources" dropdown | `source_type` | `file`, `url`, `text` |
| Date range picker | `start_date`, `end_date` | YYYY-MM-DD |
| "All Modes" dropdown | `mode` | `standard`, `enhanced` |
| Page navigation | `page` | 1, 2, 3, ... |
| Items per page selector | `limit` | 10, 20, 50, 100 |

---

## Best Practices

1. **Debounce Search**: Add 300ms debounce to title search to avoid excessive API calls

2. **Reset Page on Filter Change**: When any filter changes, reset to page 1

3. **Preserve Filters in URL**: Use query parameters to make filtered views shareable
   ```
   /saved-quizzes?source_type=file&mode=enhanced&page=2
   ```

4. **Loading States**: Show skeleton loaders during filter changes

5. **Empty States**: Handle zero results gracefully with helpful messages

6. **Error Handling**: Catch and display validation errors from the API
