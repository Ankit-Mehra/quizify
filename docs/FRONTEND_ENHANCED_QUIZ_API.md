# Frontend Integration Guide: Enhanced Quiz Generation API

## Overview

This document describes the API changes for the enhanced quiz generation system. The backend now supports a `mode` parameter that controls quiz generation quality, and responses include additional metadata (Bloom's Taxonomy level and difficulty) that can be displayed as UI badges on each question.

---

## 🚀 What's New

### 1. Generation Mode Parameter
All quiz generation endpoints now accept a `mode` parameter:
- `"standard"` (default) - Fast generation using direct LLM calls
- `"enhanced"` - RAG-based generation with semantic chunking, concept extraction, and Bloom's taxonomy classification

### 2. Enhanced Question Metadata
Each question now includes:
- `bloom_level` - Cognitive complexity level (Bloom's Taxonomy)
- `difficulty` - Question difficulty rating
- `concept_id` - Reference to the concept used for generation (optional)
- `concept_name` - Human-readable concept name, e.g., "Photosynthesis" (enhanced mode only)
- `chunk_id` - Reference to the content chunk (optional)
- `confidence_score` - AI confidence in question quality (optional)

---

## 📡 API Endpoints

### 1. Generate Quiz from Text
**POST** `/api/quiz/generate/text`

#### Request
```typescript
interface TextQuizRequest {
  title: string;              // Required: Quiz title
  content: string;            // Required: Text content (min 10 chars)
  question_type: QuestionType[]; // Default: ["mixed"]
  num_questions?: number;     // Default: 10, Range: 1-50
  mode?: "standard" | "enhanced"; // Default: "standard"
}

type QuestionType = "multiple_choice" | "true_false" | "fill_blank" | "matching" | "mixed";
```

#### Example Request
```json
{
  "title": "JavaScript Fundamentals",
  "content": "JavaScript is a versatile programming language...",
  "question_type": ["multiple_choice", "true_false"],
  "num_questions": 10,
  "mode": "enhanced"
}
```

---

### 2. Generate Quiz from File Upload
**POST** `/api/quiz/generate/file`

#### Request (multipart/form-data)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | PDF or DOCX file |
| `title` | string | Yes | Quiz title |
| `num_questions` | number | No | Default: 10, Range: 1-50 |
| `question_type` | string[] | No | Default: ["mixed"] |
| `mode` | string | No | "standard" or "enhanced" |

#### Example (JavaScript fetch)
```javascript
const formData = new FormData();
formData.append('file', file);
formData.append('title', 'My Quiz');
formData.append('num_questions', '10');
formData.append('question_type', 'multiple_choice');
formData.append('question_type', 'true_false'); // Can append multiple
formData.append('mode', 'enhanced');

const response = await fetch('/api/quiz/generate/file', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData
});
```

---

### 3. Generate Quiz from URL
**POST** `/api/quiz/generate/url`

> **Note**: URL-based generation requires Basic or Pro tier.

#### Request
```typescript
interface WebQuizRequest {
  title: string;              // Required: Quiz title
  url: string;                // Required: URL to scrape (http/https)
  question_type: QuestionType[]; // Default: ["mixed"]
  num_questions?: number;     // Default: 10, Range: 1-50
  mode?: "standard" | "enhanced"; // Default: "standard"
}
```

#### Example Request
```json
{
  "title": "Article Quiz",
  "url": "https://example.com/article",
  "question_type": ["multiple_choice"],
  "num_questions": 5,
  "mode": "enhanced"
}
```

---

### 4. Generate Quiz from Existing File ID
**POST** `/api/quiz/generate/fileid`

#### Request
```typescript
interface FileIdQuizRequest {
  title: string;              // Required: Quiz title
  file_id: string;            // Required: UUID of uploaded file
  question_type: QuestionType[]; // Default: ["mixed"]
  num_questions?: number;     // Default: 10, Range: 1-50
  mode?: "standard" | "enhanced"; // Default: "standard"
}
```

---

## 📤 Response Format

### EnhancedQuizGenerationResponse
All endpoints return this unified response:

```typescript
interface EnhancedQuizGenerationResponse {
  quiz_id: string;           // UUID of the created quiz
  title: string;             // Quiz title
  message: string;           // Success message
  questions: EnhancedQuestion[];
  generation_stats: GenerationStats;
  source_url?: string;       // Only for URL-based quizzes
  file_id?: string;          // Only for file-based quizzes
}

interface EnhancedQuestion {
  id?: string;               // UUID (present after save)
  quiz_id?: string;          // Parent quiz UUID
  type: "multiple_choice" | "true_false" | "fill_blank" | "matching";
  question: string;
  options?: string[];        // For MCQ and fill_blank
  left?: string[];           // For matching questions
  right?: string[];          // For matching questions
  correct_answer: string | boolean | number[];
  explanation: string;
  source: string;            // Source text reference
  
  // ⭐ NEW: Enhanced metadata for UI badges
  bloom_level: BloomLevel;
  difficulty: Difficulty;
  concept_id?: string;       // UUID reference
  concept_name?: string;     // Human-readable concept name (e.g., "Photosynthesis", "JavaScript Variables")
  chunk_id?: string;         // UUID reference
  confidence_score?: number; // 0.0 - 1.0
}

type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";
type Difficulty = "easy" | "medium" | "hard";

interface GenerationStats {
  mode: "standard" | "enhanced";
  questions_generated: number;
  // Enhanced mode includes additional stats:
  chunks_processed?: number;
  concepts_extracted?: number;
  total_tokens?: number;
  processing_time_ms?: number;
}
```

### Example Response
```json
{
  "quiz_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "JavaScript Fundamentals",
  "message": "Quiz generated successfully with 10 questions",
  "questions": [
    {
      "id": "q1-uuid",
      "quiz_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "type": "multiple_choice",
      "question": "What keyword is used to declare a variable in JavaScript?",
      "options": ["var", "int", "string", "define"],
      "correct_answer": "var",
      "explanation": "In JavaScript, 'var', 'let', and 'const' are used to declare variables...",
      "source": "JavaScript is a versatile programming language that uses var, let, and const...",
      "bloom_level": "remember",
      "difficulty": "easy",
      "concept_id": "concept-uuid",
      "concept_name": "Variable Declaration",
      "chunk_id": "chunk-uuid",
      "confidence_score": 0.92
    },
    {
      "id": "q2-uuid",
      "quiz_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "type": "true_false",
      "question": "JavaScript is a compiled language.",
      "correct_answer": false,
      "explanation": "JavaScript is an interpreted language, not compiled...",
      "source": "JavaScript runs in the browser as an interpreted scripting language...",
      "bloom_level": "understand",
      "difficulty": "medium"
    }
  ],
  "generation_stats": {
    "mode": "enhanced",
    "questions_generated": 10,
    "chunks_processed": 8,
    "concepts_extracted": 15,
    "total_tokens": 4250
  }
}
```

---

## 🎨 UI Implementation: Shadcn Badge Components

### TypeScript Types

```typescript
// types/quiz.ts
export type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";
export type Difficulty = "easy" | "medium" | "hard";

export interface Question {
  id?: string;
  type: "multiple_choice" | "true_false" | "fill_blank" | "matching";
  question: string;
  options?: string[];
  left?: string[];
  right?: string[];
  correct_answer: string | boolean | number[];
  explanation: string;
  source: string;
  bloom_level: BloomLevel;
  difficulty: Difficulty;
  concept_id?: string;
  concept_name?: string;  // Human-readable concept (enhanced mode only)
  chunk_id?: string;
  confidence_score?: number;
}
```

### Bloom Level Badge Component

```tsx
// components/ui/bloom-badge.tsx
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { 
  Brain, 
  Lightbulb, 
  Wrench, 
  Search, 
  Scale, 
  Sparkles 
} from "lucide-react";

type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

interface BloomBadgeProps {
  level: BloomLevel;
  showIcon?: boolean;
  className?: string;
}

const bloomConfig: Record<BloomLevel, {
  label: string;
  color: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}> = {
  remember: {
    label: "Remember",
    color: "bg-slate-100 text-slate-700 hover:bg-slate-200 border-slate-300",
    icon: Brain,
    description: "Recall facts and basic concepts"
  },
  understand: {
    label: "Understand",
    color: "bg-blue-100 text-blue-700 hover:bg-blue-200 border-blue-300",
    icon: Lightbulb,
    description: "Explain ideas or concepts"
  },
  apply: {
    label: "Apply",
    color: "bg-green-100 text-green-700 hover:bg-green-200 border-green-300",
    icon: Wrench,
    description: "Use information in new situations"
  },
  analyze: {
    label: "Analyze",
    color: "bg-yellow-100 text-yellow-700 hover:bg-yellow-200 border-yellow-300",
    icon: Search,
    description: "Draw connections among ideas"
  },
  evaluate: {
    label: "Evaluate",
    color: "bg-orange-100 text-orange-700 hover:bg-orange-200 border-orange-300",
    icon: Scale,
    description: "Justify a decision or course of action"
  },
  create: {
    label: "Create",
    color: "bg-purple-100 text-purple-700 hover:bg-purple-200 border-purple-300",
    icon: Sparkles,
    description: "Produce new or original work"
  }
};

export function BloomBadge({ level, showIcon = true, className }: BloomBadgeProps) {
  const config = bloomConfig[level];
  const Icon = config.icon;

  return (
    <Badge 
      variant="outline" 
      className={cn(
        "gap-1 font-medium border",
        config.color,
        className
      )}
      title={config.description}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {config.label}
    </Badge>
  );
}
```

### Difficulty Badge Component

```tsx
// components/ui/difficulty-badge.tsx
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Circle, CircleHalf, CircleDot } from "lucide-react";

type Difficulty = "easy" | "medium" | "hard";

interface DifficultyBadgeProps {
  difficulty: Difficulty;
  showIcon?: boolean;
  className?: string;
}

const difficultyConfig: Record<Difficulty, {
  label: string;
  color: string;
  icon: React.ComponentType<{ className?: string }>;
}> = {
  easy: {
    label: "Easy",
    color: "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 border-emerald-300",
    icon: Circle
  },
  medium: {
    label: "Medium",
    color: "bg-amber-100 text-amber-700 hover:bg-amber-200 border-amber-300",
    icon: CircleHalf
  },
  hard: {
    label: "Hard",
    color: "bg-red-100 text-red-700 hover:bg-red-200 border-red-300",
    icon: CircleDot
  }
};

export function DifficultyBadge({ difficulty, showIcon = true, className }: DifficultyBadgeProps) {
  const config = difficultyConfig[difficulty];
  const Icon = config.icon;

  return (
    <Badge 
      variant="outline" 
      className={cn(
        "gap-1 font-medium border",
        config.color,
        className
      )}
    >
      {showIcon && <Icon className="h-3 w-3" />}
      {config.label}
    </Badge>
  );
}
```

### Usage in Question Card

```tsx
// components/question-card.tsx
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BloomBadge } from "@/components/ui/bloom-badge";
import { DifficultyBadge } from "@/components/ui/difficulty-badge";
import { Lightbulb } from "lucide-react";
import type { Question } from "@/types/quiz";

interface QuestionCardProps {
  question: Question;
  index: number;
}

export function QuestionCard({ question, index }: QuestionCardProps) {
  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Question {index + 1}
          </span>
          <div className="flex flex-wrap gap-2">
            {/* Concept badge - only shows in enhanced mode */}
            {question.concept_name && (
              <Badge 
                variant="outline" 
                className="gap-1 bg-indigo-50 text-indigo-700 border-indigo-200"
              >
                <Lightbulb className="h-3 w-3" />
                {question.concept_name}
              </Badge>
            )}
            <BloomBadge level={question.bloom_level} />
            <DifficultyBadge difficulty={question.difficulty} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-lg font-medium mb-4">{question.question}</p>
        
        {question.type === "multiple_choice" && question.options && (
          <div className="space-y-2">
            {question.options.map((option, i) => (
              <div
                key={i}
                className={cn(
                  "p-3 rounded-md border",
                  option === question.correct_answer
                    ? "border-green-500 bg-green-50"
                    : "border-gray-200"
                )}
              >
                {option}
              </div>
            ))}
          </div>
        )}

        {question.type === "true_false" && (
          <div className="flex gap-4">
            <div className={cn(
              "px-4 py-2 rounded-md border",
              question.correct_answer === true
                ? "border-green-500 bg-green-50"
                : "border-gray-200"
            )}>
              True
            </div>
            <div className={cn(
              "px-4 py-2 rounded-md border",
              question.correct_answer === false
                ? "border-green-500 bg-green-50"
                : "border-gray-200"
            )}>
              False
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

### Mode Selection UI

```tsx
// components/quiz-generator-form.tsx
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Zap, Sparkles } from "lucide-react";

interface ModeSelectionProps {
  value: "standard" | "enhanced";
  onChange: (value: "standard" | "enhanced") => void;
}

export function ModeSelection({ value, onChange }: ModeSelectionProps) {
  return (
    <RadioGroup value={value} onValueChange={onChange} className="grid grid-cols-2 gap-4">
      <div>
        <RadioGroupItem value="standard" id="standard" className="peer sr-only" />
        <Label
          htmlFor="standard"
          className="flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-primary [&:has([data-state=checked])]:border-primary cursor-pointer"
        >
          <Zap className="mb-3 h-6 w-6" />
          <span className="text-sm font-semibold">Standard</span>
          <span className="text-xs text-muted-foreground text-center mt-1">
            Fast generation
          </span>
        </Label>
      </div>
      <div>
        <RadioGroupItem value="enhanced" id="enhanced" className="peer sr-only" />
        <Label
          htmlFor="enhanced"
          className="flex flex-col items-center justify-between rounded-md border-2 border-muted bg-popover p-4 hover:bg-accent hover:text-accent-foreground peer-data-[state=checked]:border-primary [&:has([data-state=checked])]:border-primary cursor-pointer"
        >
          <Sparkles className="mb-3 h-6 w-6" />
          <span className="text-sm font-semibold">Enhanced</span>
          <span className="text-xs text-muted-foreground text-center mt-1">
            Higher quality with Bloom's taxonomy
          </span>
        </Label>
      </div>
    </RadioGroup>
  );
}
```

---

## 📊 Bloom's Taxonomy Reference

| Level | Description | Question Examples |
|-------|-------------|-------------------|
| **Remember** | Recall facts and basic concepts | "What is...", "Name the...", "List the..." |
| **Understand** | Explain ideas or concepts | "Explain why...", "Summarize...", "Describe..." |
| **Apply** | Use information in new situations | "How would you use...", "Calculate...", "Demonstrate..." |
| **Analyze** | Draw connections among ideas | "Compare and contrast...", "What is the relationship...", "Why did..." |
| **Evaluate** | Justify a decision or course of action | "Do you agree that...", "What is most important...", "Assess..." |
| **Create** | Produce new or original work | "Design a...", "What would happen if...", "Propose..." |

---

## 🔄 Migration Notes

### Breaking Changes
None - the API is backward compatible. The `mode` parameter defaults to `"standard"` if not provided.

### New Fields
Questions now include optional enhanced metadata fields. These will be:
- **Always present** when `mode: "enhanced"` is used
- **Sometimes present** when `mode: "standard"` (basic defaults may be assigned)

### Recommended Frontend Changes
1. Add `mode` selection to quiz generation forms
2. Display Bloom level and difficulty badges on question cards
3. Optionally show `confidence_score` as a quality indicator
4. Use `generation_stats` to show processing details to users

---

## 🧪 Testing

### Test Enhanced Mode
```bash
curl -X POST "https://your-api.com/api/quiz/generate/text" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Quiz",
    "content": "Your educational content here...",
    "num_questions": 5,
    "mode": "enhanced"
  }'
```

### Verify Response Contains Metadata
```javascript
const response = await generateQuiz({ ...params, mode: "enhanced" });

// All questions should have bloom_level and difficulty
response.questions.forEach(q => {
  console.assert(q.bloom_level !== undefined, "Missing bloom_level");
  console.assert(q.difficulty !== undefined, "Missing difficulty");
});
```

---

## 📝 Changelog

### v2.0.0 (December 2024)
- Added `mode` parameter to all quiz generation endpoints
- Added `bloom_level` and `difficulty` to question responses
- Added `generation_stats` to responses for enhanced mode
- Unified all endpoints to return `EnhancedQuizGenerationResponse`
- Added optional `concept_id`, `chunk_id`, and `confidence_score` fields
