# Frontend Integration Guide: Quiz Export Feature

This document provides everything needed to integrate the quiz export functionality into the Quizify frontend.

---

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [TypeScript Types](#typescript-types)
4. [React Hooks & Services](#react-hooks--services)
5. [UI Components](#ui-components)
6. [Tier-Based Access Control](#tier-based-access-control)
7. [Error Handling](#error-handling)
8. [Usage Examples](#usage-examples)

---

## Overview

The export feature allows users to download quizzes in various formats. 

> **Updated December 2025**: Export is now **free for all tiers** who own a quiz. The only gating is on quiz generation (credits). If a user generated a quiz with their credits, they can export it in any format.

| Tier | Price | Available Formats |
|------|-------|-------------------|
| **Free** | $0 | ✅ All 8 formats (PDF, DOCX, CSV, Share Link, QTI, Moodle XML, Google Forms) |
| **Pro** | $20/mo | ✅ All 8 formats (same as Free) |

> **Note:** All users can export their quizzes in any format. The differentiation is in quiz generation credits, not export capabilities.

---

## API Endpoints

### Base URL
```
/api/quizzes
```

### 1. Export Quiz

**Endpoint:** `POST /api/quizzes/{quiz_id}/export`

**Headers:**
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "format": "pdf",
  "include_answer_key": true,
  "include_explanations": false
}
```

**Supported Formats:**
- `pdf` - PDF document (printable)
- `docx` - Word document (editable)
- `csv_quizify` - CSV native format
- `csv_anki` - CSV for Anki flashcards
- `share_link` - Generate public share URL
- `google_forms` - Export to Google Forms
- `qti` - QTI 2.1 XML (LMS)
- `moodle_xml` - Moodle XML (LMS)

> **Note:** All formats are available to all tiers. No tier restrictions on export.

**Response:**
- **File formats** (pdf, docx, csv_*, qti, moodle_xml): Returns binary file with appropriate `Content-Type` and `Content-Disposition` headers
- **share_link format**: Returns JSON:
  ```json
  {
    "share_url": "https://app.quizify.ca/share/abc123"
  }
  ```

**Status Codes:**
| Code | Description |
|------|-------------|
| 200 | Export successful |
| 401 | Not authenticated |
| 403 | Not quiz owner OR tier insufficient |
| 404 | Quiz not found |
| 422 | Invalid format or empty quiz |
| 500 | Export failed |

---

### 2. Get Available Formats

**Endpoint:** `GET /api/quizzes/export/formats`

**Headers:**
```
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "pdf": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "PDF Document"
  },
  "docx": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "Word Document (DOCX)"
  },
  "csv_quizify": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "CSV (Quizify Native)"
  },
  "csv_anki": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "CSV (Anki Flashcards)"
  },
  "share_link": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "Shareable Link"
  },
  "google_forms": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "Google Forms"
  },
  "qti": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "QTI 2.1 (LMS)"
  },
  "moodle_xml": {
    "available": true,
    "requires_pro": false,
    "requires_paid": false,
    "coming_soon": false,
    "name": "Moodle XML (LMS)"
  }
}
```

> **Note:** Response is a flat object (not nested under `formats`), and does not include `user_tier` or `description` fields.
> **Updated December 2025:** All formats are now available to all tiers. `requires_pro` and `requires_paid` are always `false`.

---

### 3. Share Link Management

#### Create Share Link
**Endpoint:** `POST /api/share`

**Request:**
```json
{
  "quiz_id": "uuid-of-quiz"
}
```

**Response:**
```json
{
  "quiz_id": "uuid-of-quiz",
  "public_slug": "abc123",
  "share_url": "https://app.quizify.ca/share/abc123",
  "is_public": true,
  "shared_at": "2025-11-26T10:30:00Z"
}
```

#### Revoke Share Link
**Endpoint:** `DELETE /api/share/{quiz_id}`

**Response:**
```json
{
  "message": "Share link revoked successfully",
  "is_public": false
}
```

#### Get Share Status
**Endpoint:** `GET /api/share/status/{quiz_id}`

**Response:**
```json
{
  "quiz_id": "uuid-of-quiz",
  "is_public": true,
  "public_slug": "abc123",
  "share_url": "https://app.quizify.ca/share/abc123",
  "shared_at": "2025-11-26T10:30:00Z"
}
```

#### View Public Quiz (No Auth Required)
**Endpoint:** `GET /api/share/public/{slug}`

**Response:**
```json
{
  "id": "uuid-of-quiz",
  "title": "My Quiz",
  "description": null,
  "topic": null,
  "total_questions": 10,
  "questions": [
    {
      "id": "question-uuid-1",
      "question_number": 1,
      "question_type": "multiple_choice",
      "question_text": "What is 2+2?",
      "options": [
        {"id": "a", "text": "3"},
        {"id": "b", "text": "4"},
        {"id": "c", "text": "5"},
        {"id": "d", "text": "6"}
      ],
      "difficulty": null
    },
    {
      "id": "question-uuid-2",
      "question_number": 2,
      "question_type": "matching",
      "question_text": "Match the capitals:",
      "matching_left": ["USA", "UK", "France"],
      "matching_right": ["Paris", "London", "Washington DC"],
      "difficulty": null
    }
  ],
  "shared_at": "2025-11-26T10:30:00Z"
}
```

> **Note:** Public quiz does NOT include correct answers to prevent cheating.
> **Note:** For matching questions, `matching_right` is shuffled server-side so the order does not reveal the correct pairings.
> **Note:** `description`, `topic`, and `difficulty` are always `null` as these fields are not stored in the database.

---

## TypeScript Types

```typescript
// ============================================================================
// Export Types
// ============================================================================

export type ExportFormat = 
  | 'pdf'
  | 'docx'
  | 'csv_quizify'
  | 'csv_anki'
  | 'qti'
  | 'moodle_xml'
  | 'share_link'
  | 'google_forms';

export type UserTier = 'free' | 'premium' | 'pro';

export interface ExportRequest {
  format: ExportFormat;
  include_answer_key?: boolean;  // default: true
  include_explanations?: boolean; // default: false
}

export interface ShareLinkResponse {
  share_url: string;
}

export interface FormatInfo {
  available: boolean;
  requires_pro: boolean;
  requires_paid: boolean;  // Requires Premium or Pro
  coming_soon: boolean;    // Pro features not yet released
  name: string;
}

// Response is a flat Record, not nested under 'formats'
export type AvailableFormatsResponse = Record<ExportFormat, FormatInfo>;

// ============================================================================
// Share Link Types
// ============================================================================

export interface ShareLinkCreateRequest {
  quiz_id: string;
}

export interface ShareLinkStatusResponse {
  quiz_id: string;
  is_public: boolean;
  public_slug?: string;
  share_url?: string;
  shared_at?: string;
}

export interface PublicQuestionOption {
  id: string;  // 'a', 'b', 'c', 'd'
  text: string;
}

export interface PublicQuizQuestion {
  id: string;
  question_number: number;
  question_type: 'multiple_choice' | 'true_false' | 'fill_blank' | 'matching';
  question_text: string;
  options?: PublicQuestionOption[];  // For multiple_choice/true_false
  // Matching question fields - left and right columns shown separately
  // Right column is shuffled server-side to prevent answer leakage
  matching_left?: string[];   // Left column items (numbered 1, 2, 3...)
  matching_right?: string[];  // Right column items (shuffled, lettered a, b, c...)
  difficulty: null;  // Always null - not stored in DB
}

export interface PublicQuizView {
  id: string;  // Note: 'id' not 'quiz_id'
  title: string;
  description: null;  // Always null - column doesn't exist in DB
  topic: null;  // Always null - column doesn't exist in DB
  total_questions: number;  // Note: 'total_questions' not 'question_count'
  questions: PublicQuizQuestion[];
  shared_at: string;
  // Note: no 'created_at' in public view
}

// ============================================================================
// Error Types
// ============================================================================

export interface ExportError {
  detail: string;
}

export interface TierInsufficientError {
  error: 'tier_insufficient';
  message: string;
  required_tier: 'premium' | 'pro';  // 'premium' for free users, 'pro' for Google Forms/LMS formats
  current_tier: string;
  requested_format: string;  // The format that was requested
  upgrade_url?: string;      // URL to upgrade page
}
```

---

## React Hooks & Services

### Export Service

```typescript
// services/exportService.ts

import { api } from './api';
import type { 
  ExportFormat, 
  ExportRequest, 
  AvailableFormatsResponse,
  ShareLinkResponse 
} from '@/types/export';

const EXPORT_BASE_URL = '/api/quizzes';

/**
 * Export a quiz to the specified format.
 * 
 * For file formats: triggers download
 * For share_link: returns the share URL
 */
export async function exportQuiz(
  quizId: string,
  options: ExportRequest
): Promise<Blob | ShareLinkResponse> {
  const response = await api.post(
    `${EXPORT_BASE_URL}/${quizId}/export`,
    options,
    {
      responseType: options.format === 'share_link' ? 'json' : 'blob',
    }
  );

  return response.data;
}

/**
 * Download export as file (handles blob response)
 */
export async function downloadExport(
  quizId: string,
  quizTitle: string,
  options: ExportRequest
): Promise<void> {
  const response = await api.post(
    `${EXPORT_BASE_URL}/${quizId}/export`,
    options,
    { responseType: 'blob' }
  );

  // Get filename from Content-Disposition header or generate one
  const contentDisposition = response.headers['content-disposition'];
  let filename = `${quizTitle}.${getFileExtension(options.format)}`;
  
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="?(.+)"?/);
    if (match) filename = match[1];
  }

  // Trigger browser download
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Get available export formats for current user
 * Returns flat object keyed by format name
 */
export async function getAvailableFormats(): Promise<AvailableFormatsResponse> {
  const response = await api.get(`${EXPORT_BASE_URL}/export/formats`);
  return response.data;
}

/**
 * Helper to get user tier from formats response
 * (tier must be inferred from format availability since it's not returned)
 */
export function inferUserTier(formats: AvailableFormatsResponse): UserTier {
  // If PDF is available, user is at least Premium
  if (formats.pdf?.available) return 'premium';
  // Otherwise Free
  return 'free';
}

/**
 * Check if a format requires Pro tier
 */
export function isFormatProOnly(formats: AvailableFormatsResponse, format: ExportFormat): boolean {
  return formats[format]?.requires_pro ?? false;
}

/**
 * Map format to file extension
 */
function getFileExtension(format: ExportFormat): string {
  const extensions: Record<ExportFormat, string> = {
    pdf: 'pdf',
    docx: 'docx',
    csv_quizify: 'csv',
    csv_anki: 'csv',
    qti: 'zip',      // QTI exports as ZIP with manifest
    moodle_xml: 'xml',
    share_link: '',  // Not a file download
  };
  return extensions[format];
}
```

### Share Service

```typescript
// services/shareService.ts

import { api } from './api';
import type { 
  ShareLinkStatusResponse, 
  PublicQuizView 
} from '@/types/export';

const SHARE_BASE_URL = '/api/share';

/**
 * Create a share link for a quiz
 */
export async function createShareLink(quizId: string): Promise<ShareLinkStatusResponse> {
  const response = await api.post(SHARE_BASE_URL, { quiz_id: quizId });
  return response.data;
}

/**
 * Revoke a share link (make quiz private)
 */
export async function revokeShareLink(quizId: string): Promise<void> {
  await api.delete(`${SHARE_BASE_URL}/${quizId}`);
}

/**
 * Get share status for a quiz
 */
export async function getShareStatus(quizId: string): Promise<ShareLinkStatusResponse> {
  const response = await api.get(`${SHARE_BASE_URL}/status/${quizId}`);
  return response.data;
}

/**
 * Get public quiz by slug (no auth required)
 */
export async function getPublicQuiz(slug: string): Promise<PublicQuizView> {
  const response = await api.get(`${SHARE_BASE_URL}/public/${slug}`);
  return response.data;
}
```

### React Hook

```typescript
// hooks/useExport.ts

import { useState, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { 
  exportQuiz, 
  downloadExport, 
  getAvailableFormats,
  inferUserTier 
} from '@/services/exportService';
import { 
  createShareLink, 
  revokeShareLink, 
  getShareStatus 
} from '@/services/shareService';
import type { ExportFormat, ExportRequest } from '@/types/export';
import { toast } from 'sonner';

export function useExport(quizId: string, quizTitle: string) {
  const queryClient = useQueryClient();
  const [isExporting, setIsExporting] = useState(false);

  // Fetch available formats
  const { data: formatsData, isLoading: formatsLoading } = useQuery({
    queryKey: ['export-formats'],
    queryFn: getAvailableFormats,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  // Infer user tier from format availability
  const userTier = formatsData ? inferUserTier(formatsData) : 'free';

  // Fetch share status
  const { data: shareStatus, isLoading: shareLoading } = useQuery({
    queryKey: ['share-status', quizId],
    queryFn: () => getShareStatus(quizId),
    enabled: !!quizId,
  });

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async (options: ExportRequest) => {
      if (options.format === 'share_link') {
        return createShareLink(quizId);
      }
      return downloadExport(quizId, quizTitle, options);
    },
    onSuccess: (_, variables) => {
      if (variables.format === 'share_link') {
        queryClient.invalidateQueries({ queryKey: ['share-status', quizId] });
        toast.success('Share link created!');
      } else {
        toast.success('Export downloaded!');
      }
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Export failed';
      toast.error(message);
    },
  });

  // Revoke share link mutation
  const revokeMutation = useMutation({
    mutationFn: () => revokeShareLink(quizId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['share-status', quizId] });
      toast.success('Share link revoked');
    },
    onError: () => {
      toast.error('Failed to revoke share link');
    },
  });

  const handleExport = useCallback(
    async (format: ExportFormat, options?: Partial<ExportRequest>) => {
      setIsExporting(true);
      try {
        await exportMutation.mutateAsync({
          format,
          include_answer_key: options?.include_answer_key ?? true,
          include_explanations: options?.include_explanations ?? false,
        });
      } finally {
        setIsExporting(false);
      }
    },
    [exportMutation]
  );

  const handleRevokeShare = useCallback(async () => {
    await revokeMutation.mutateAsync();
  }, [revokeMutation]);

  return {
    // State
    isExporting: isExporting || exportMutation.isPending,
    isLoading: formatsLoading || shareLoading,
    
    // Data
    formats: formatsData,  // Flat object, not nested
    userTier,  // Inferred from format availability
    shareStatus,
    
    // Actions
    exportQuiz: handleExport,
    revokeShareLink: handleRevokeShare,
    
    // Helpers
    isFormatAvailable: (format: ExportFormat) => 
      formatsData?.[format]?.available ?? false,
    isFormatProOnly: (format: ExportFormat) =>
      formatsData?.[format]?.requires_pro ?? false,
    requiresPro: (format: ExportFormat) => 
      formatsData?.[format]?.requires_pro ?? false,
  };
}
```

---

## UI Components

### Export Button with Dropdown

```tsx
// components/ExportDropdown.tsx

import { useState } from 'react';
import { Download, Share2, FileText, Table, Crown, Loader2, Clock } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useExport } from '@/hooks/useExport';
import type { ExportFormat } from '@/types/export';

interface ExportDropdownProps {
  quizId: string;
  quizTitle: string;
  disabled?: boolean;
}

const FORMAT_OPTIONS: Array<{
  format: ExportFormat;
  label: string;
  icon: typeof Download;
  group: 'document' | 'data' | 'lms' | 'share';
}> = [
  { format: 'pdf', label: 'PDF Document', icon: FileText, group: 'document' },
  { format: 'docx', label: 'Word Document', icon: FileText, group: 'document' },
  { format: 'csv_quizify', label: 'CSV (Quizify)', icon: Table, group: 'data' },
  { format: 'csv_anki', label: 'CSV (Anki)', icon: Table, group: 'data' },
  { format: 'qti', label: 'QTI 2.1 (LMS)', icon: Download, group: 'lms' },
  { format: 'moodle_xml', label: 'Moodle XML', icon: Download, group: 'lms' },
  { format: 'google_forms', label: 'Google Forms', icon: Share2, group: 'lms' },
  { format: 'share_link', label: 'Create Share Link', icon: Share2, group: 'share' },
];

export function ExportDropdown({ quizId, quizTitle, disabled }: ExportDropdownProps) {
  const [open, setOpen] = useState(false);
  
  const {
    isExporting,
    formats,
    userTier,
    exportQuiz,
    isFormatAvailable,
    isFormatProOnly,
  } = useExport(quizId, quizTitle);

  const handleSelect = async (format: ExportFormat) => {
    // Don't allow clicking on Pro-only formats if not Pro tier
    if (formats?.[format]?.requires_pro && userTier !== 'pro') {
      return;
    }
    setOpen(false);
    await exportQuiz(format);
  };

  // Group formats
  const documentFormats = FORMAT_OPTIONS.filter(f => f.group === 'document');
  const dataFormats = FORMAT_OPTIONS.filter(f => f.group === 'data');
  const lmsFormats = FORMAT_OPTIONS.filter(f => f.group === 'lms');
  const shareFormats = FORMAT_OPTIONS.filter(f => f.group === 'share');

  // Check if user has any export access
  const hasExportAccess = userTier !== 'free';

  if (!hasExportAccess) {
    return (
      <Button variant="outline" disabled>
        <Download className="h-4 w-4 mr-2" />
        Export
        <Badge variant="secondary" className="ml-2">
          Premium
        </Badge>
      </Button>
    );
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={disabled || isExporting}>
          {isExporting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Download className="h-4 w-4 mr-2" />
          )}
          Export
        </Button>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Document Formats</DropdownMenuLabel>
        {documentFormats.map(({ format, label, icon: Icon }) => (
          <DropdownMenuItem
            key={format}
            onClick={() => handleSelect(format)}
            disabled={!isFormatAvailable(format)}
          >
            <Icon className="h-4 w-4 mr-2" />
            {label}
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuLabel>Data Formats</DropdownMenuLabel>
        {dataFormats.map(({ format, label, icon: Icon }) => (
          <DropdownMenuItem
            key={format}
            onClick={() => handleSelect(format)}
            disabled={!isFormatAvailable(format)}
          >
            <Icon className="h-4 w-4 mr-2" />
            {label}
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuLabel>LMS Formats (Pro)</DropdownMenuLabel>
        {lmsFormats.map(({ format, label, icon: Icon }) => {
          const requiresPro = formats?.[format]?.requires_pro;
          const isProUser = userTier === 'pro';
          return (
            <DropdownMenuItem
              key={format}
              onClick={() => handleSelect(format)}
              disabled={requiresPro && !isProUser}
              className={requiresPro && !isProUser ? "flex items-center justify-between opacity-60" : "flex items-center justify-between"}
            >
              <span className="flex items-center">
                <Icon className="h-4 w-4 mr-2" />
                {label}
              </span>
              {requiresPro && !isProUser && (
                <Badge variant="outline" className="ml-2 text-xs">
                  <Crown className="h-3 w-3 mr-1" />
                  Pro
                </Badge>
              )}
            </DropdownMenuItem>
          );
        })}

        <DropdownMenuSeparator />
        {shareFormats.map(({ format, label, icon: Icon }) => (
          <DropdownMenuItem
            key={format}
            onClick={() => handleSelect(format)}
            disabled={!isFormatAvailable(format)}
          >
            <Icon className="h-4 w-4 mr-2" />
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

### Export Options Dialog

```tsx
// components/ExportOptionsDialog.tsx

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Loader2 } from 'lucide-react';
import type { ExportFormat } from '@/types/export';

interface ExportOptionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  format: ExportFormat;
  formatName: string;
  onExport: (options: { include_answer_key: boolean; include_explanations: boolean }) => Promise<void>;
  isExporting: boolean;
}

export function ExportOptionsDialog({
  open,
  onOpenChange,
  format,
  formatName,
  onExport,
  isExporting,
}: ExportOptionsDialogProps) {
  const [includeAnswerKey, setIncludeAnswerKey] = useState(true);
  const [includeExplanations, setIncludeExplanations] = useState(false);

  const handleExport = async () => {
    await onExport({
      include_answer_key: includeAnswerKey,
      include_explanations: includeExplanations,
    });
    onOpenChange(false);
  };

  // Share link doesn't need options
  if (format === 'share_link') {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Export as {formatName}</DialogTitle>
          <DialogDescription>
            Configure your export options
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="answer-key" className="flex flex-col gap-1">
              <span>Include Answer Key</span>
              <span className="text-sm text-muted-foreground font-normal">
                Show correct answers in the export
              </span>
            </Label>
            <Switch
              id="answer-key"
              checked={includeAnswerKey}
              onCheckedChange={setIncludeAnswerKey}
            />
          </div>

          <div className="flex items-center justify-between">
            <Label htmlFor="explanations" className="flex flex-col gap-1">
              <span>Include Explanations</span>
              <span className="text-sm text-muted-foreground font-normal">
                Add explanation text for each answer
              </span>
            </Label>
            <Switch
              id="explanations"
              checked={includeExplanations}
              onCheckedChange={setIncludeExplanations}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleExport} disabled={isExporting}>
            {isExporting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Export
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### Share Link Card

```tsx
// components/ShareLinkCard.tsx

import { useState } from 'react';
import { Copy, ExternalLink, Trash2, Share2, Check } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useExport } from '@/hooks/useExport';
import { toast } from 'sonner';

interface ShareLinkCardProps {
  quizId: string;
  quizTitle: string;
}

export function ShareLinkCard({ quizId, quizTitle }: ShareLinkCardProps) {
  const [copied, setCopied] = useState(false);
  
  const {
    shareStatus,
    isExporting,
    exportQuiz,
    revokeShareLink,
  } = useExport(quizId, quizTitle);

  const handleCopy = async () => {
    if (shareStatus?.share_url) {
      await navigator.clipboard.writeText(shareStatus.share_url);
      setCopied(true);
      toast.success('Link copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCreateLink = async () => {
    await exportQuiz('share_link');
  };

  if (!shareStatus?.is_public) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Share2 className="h-5 w-5" />
            Share Quiz
          </CardTitle>
          <CardDescription>
            Create a public link to share this quiz with others
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button 
            onClick={handleCreateLink} 
            disabled={isExporting}
            className="w-full"
          >
            <Share2 className="h-4 w-4 mr-2" />
            Create Share Link
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Share2 className="h-5 w-5" />
          Share Link Active
        </CardTitle>
        <CardDescription>
          Anyone with this link can view your quiz
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input 
            value={shareStatus.share_url} 
            readOnly 
            className="font-mono text-sm"
          />
          <Button variant="outline" size="icon" onClick={handleCopy}>
            {copied ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => window.open(shareStatus.share_url, '_blank')}
          >
            <ExternalLink className="h-4 w-4" />
          </Button>
        </div>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm" className="w-full">
              <Trash2 className="h-4 w-4 mr-2" />
              Revoke Share Link
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Revoke share link?</AlertDialogTitle>
              <AlertDialogDescription>
                This will make the quiz private again. Anyone with the old link 
                will no longer be able to access it.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={revokeShareLink}>
                Revoke Link
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <p className="text-xs text-muted-foreground text-center">
          Shared on {new Date(shareStatus.shared_at!).toLocaleDateString()}
        </p>
      </CardContent>
    </Card>
  );
}
```

---

## Tier-Based Access Control

> **Updated December 2025**: Export is now free for all tiers. The TierGate component below is preserved for historical reference and potential future use, but is no longer enforced for export features.

### Tier Gate Component (Historical - No Longer Enforced for Exports)

```tsx
// components/TierGate.tsx
// NOTE: This component is no longer needed for export features.
// All tiers can export in all formats as of December 2025.
// Keeping for potential future premium features beyond exports.

import { Crown, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';

interface TierGateProps {
  requiredTier: 'premium' | 'pro';
  currentTier: 'free' | 'premium' | 'pro';
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

const TIER_ORDER = { free: 0, premium: 1, pro: 2 };

export function TierGate({ 
  requiredTier, 
  currentTier, 
  children, 
  fallback 
}: TierGateProps) {
  const router = useRouter();
  
  const hasAccess = TIER_ORDER[currentTier] >= TIER_ORDER[requiredTier];

  if (hasAccess) {
    return <>{children}</>;
  }

  if (fallback) {
    return <>{fallback}</>;
  }

  return (
    <div className="flex flex-col items-center justify-center p-6 text-center bg-muted/50 rounded-lg">
      <Crown className="h-8 w-8 text-yellow-500 mb-2" />
      <h3 className="font-semibold">{requiredTier === 'pro' ? 'Pro Feature' : 'Premium Feature'}</h3>
      <p className="text-sm text-muted-foreground mb-4">
        Upgrade to {requiredTier === 'pro' ? 'Pro' : 'Premium'} to access this feature
      </p>
      <Button onClick={() => router.push('/billing/upgrade')}>
        Upgrade Now
      </Button>
    </div>
  );
}
```

---

## Error Handling

### Error Handler Utility

```typescript
// utils/exportErrors.ts

import { toast } from 'sonner';

export function handleExportError(error: any): void {
  const status = error.response?.status;
  const detail = error.response?.data?.detail;
  const errorType = error.response?.data?.error;

  switch (status) {
    case 401:
      toast.error('Please log in to export quizzes');
      break;
      
    case 403:
      if (errorType === 'tier_insufficient') {
        const requiredTier = error.response?.data?.required_tier;
        if (requiredTier === 'pro') {
          toast.error('Upgrade to Pro to access this feature', {
            description: 'Google Forms, QTI, and Moodle XML exports require Pro tier.',
            action: {
              label: 'Upgrade to Pro',
              onClick: () => window.location.href = '/billing/upgrade',
            },
          });
        } else {
          toast.error('Upgrade to Premium to access export features', {
            action: {
              label: 'Upgrade - $7/mo',
              onClick: () => window.location.href = '/billing/upgrade',
            },
          });
        }
      } else {
        toast.error('You do not have permission to export this quiz');
      }
      break;
      
    case 404:
      toast.error('Quiz not found');
      break;
      
    case 422:
      toast.error(detail || 'Invalid export request');
      break;
      
    case 500:
      toast.error('Export failed. Please try again later.');
      break;
      
    default:
      toast.error('An unexpected error occurred');
  }
}
```

---

## Usage Examples

### Basic Export Button in Quiz Card

```tsx
// In a quiz list or detail page
import { ExportDropdown } from '@/components/ExportDropdown';

function QuizCard({ quiz }) {
  return (
    <div className="p-4 border rounded-lg">
      <h3>{quiz.title}</h3>
      <p>{quiz.question_count} questions</p>
      
      <div className="flex gap-2 mt-4">
        <Button variant="outline">Edit</Button>
        <ExportDropdown 
          quizId={quiz.id} 
          quizTitle={quiz.title} 
        />
      </div>
    </div>
  );
}
```

### Public Quiz Page (for share links)

> ⚠️ **SECURITY WARNING: XSS Prevention Required**
> 
> Public quiz responses contain **user-authored content** (quiz titles, question text, options).
> This content is NOT sanitized server-side and MUST be treated as untrusted input.
> 
> **Required mitigations:**
> - Use React's built-in JSX escaping (automatic for `{variable}` in JSX)
> - Never use `dangerouslySetInnerHTML` with quiz content
> - Sanitize with DOMPurify if you MUST render HTML (not recommended)
> - Same applies to: `quiz.title`, `quiz.description`, `question.question_text`, `option.text`

```tsx
// pages/share/[slug].tsx
import { useQuery } from '@tanstack/react-query';
import { getPublicQuiz } from '@/services/shareService';

export default function PublicQuizPage({ params }: { params: { slug: string } }) {
  const { data: quiz, isLoading, error } = useQuery({
    queryKey: ['public-quiz', params.slug],
    queryFn: () => getPublicQuiz(params.slug),
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <NotFound message="Quiz not found or no longer shared" />;

  return (
    <div className="container max-w-3xl py-8">
      {/* React JSX auto-escapes these values - safe from XSS */}
      <h1 className="text-2xl font-bold">{quiz.title}</h1>
      {/* Note: description and topic are always null */}
      <p className="text-sm">{quiz.total_questions} questions</p>
      
      <div className="mt-8 space-y-6">
        {quiz.questions.map((q, i) => (
          <QuestionDisplay key={q.id} question={q} number={i + 1} />
        ))}
      </div>
    </div>
  );
}
```

---

## Testing

### Mock Data for Development

```typescript
// mocks/exportMocks.ts

// Mock for Premium tier user
export const mockFormatsResponse: AvailableFormatsResponse = {
  pdf: { available: true, requires_pro: false, requires_paid: false, coming_soon: false, name: 'PDF Document' },
  docx: { available: true, requires_pro: false, requires_paid: false, coming_soon: false, name: 'Word Document (DOCX)' },
  csv_quizify: { available: true, requires_pro: false, requires_paid: false, coming_soon: false, name: 'CSV (Quizify Native)' },
  csv_anki: { available: true, requires_pro: false, requires_paid: false, coming_soon: false, name: 'CSV (Anki Flashcards)' },
  share_link: { available: true, requires_pro: false, requires_paid: false, coming_soon: false, name: 'Shareable Link' },
  google_forms: { available: false, requires_pro: true, requires_paid: false, coming_soon: false, name: 'Google Forms' },
  qti: { available: false, requires_pro: true, requires_paid: false, coming_soon: false, name: 'QTI 2.1 (LMS)' },
  moodle_xml: { available: false, requires_pro: true, requires_paid: false, coming_soon: false, name: 'Moodle XML (LMS)' },
};

export const mockShareStatus = {
  quiz_id: 'abc-123',
  is_public: true,
  public_slug: 'xyz789',
  share_url: 'https://app.quizify.ca/share/xyz789',
  shared_at: '2025-11-26T10:30:00Z',
};
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-27 | 2.1.0 | **Breaking:** Google Forms moved to Pro-only tier. Pro tier now fully enabled (no more "coming soon"). Premium tier has 5 formats, Pro tier has 8 formats (includes QTI, Moodle XML, Google Forms). |
| 2025-11-27 | 2.0.0 | **Breaking:** Renamed "Basic" tier to "Premium" ($7/mo). Pro tier features (QTI, Moodle XML) now return `coming_soon: true` and are disabled. Added `google_forms` export format. New fields: `requires_paid`, `coming_soon` in format response. |
| 2025-11-26 | 1.2.0 | **Updated:** `description`, `topic`, and `difficulty` are now always `null` (not stored in DB). `question_type` uses `multiple_choice` instead of `mcq`. Added XSS security warning for frontend. |
| 2025-11-26 | 1.1.0 | **Breaking:** Matching questions now use `matching_left`/`matching_right` arrays instead of `matching_pairs`. Right column is shuffled server-side for security. |
| 2025-11-26 | 1.0.0 | Initial integration guide |
