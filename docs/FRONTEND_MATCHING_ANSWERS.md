# Matching Question Answer Display

## Overview

The submission review API now returns `left` and `right` arrays for matching questions, enabling human-readable answer display.

---

## API Response

```typescript
interface QuestionReviewDetail {
  question_type: "matching";
  your_answer: number[];        // Indices: [3, 1, 1, 0]
  correct_answer: number[];     // Indices: [0, 1, 2, 3]
  left?: string[] | null;       // ["OpenAI", "Google", "Microsoft", "Forrester"]
  right?: string[] | null;      // ["Atlas", "Chrome", "Edge", "Research"]
  // ... other fields
}
```

---

## How It Works

The answer arrays contain **indices into the `right` array** for each item in `left`:

```
left[0] = "OpenAI"     → your_answer[0] = 3 → right[3] = "Research"
left[1] = "Google"     → your_answer[1] = 1 → right[1] = "Chrome"
left[2] = "Microsoft"  → your_answer[2] = 1 → right[1] = "Chrome"
left[3] = "Forrester"  → your_answer[3] = 0 → right[0] = "Atlas"
```

---

## Display Implementation

```typescript
function formatMatchingAnswer(
  answer: number[],
  left: string[],
  right: string[]
): string {
  if (!left || !right || !answer) {
    // Fallback to indices if data missing
    return answer?.join(", ") || "No answer";
  }
  
  return answer
    .map((rightIdx, leftIdx) => `${left[leftIdx]} → ${right[rightIdx]}`)
    .join(", ");
}

// Usage
const display = formatMatchingAnswer(
  question.your_answer,  // [3, 1, 1, 0]
  question.left,         // ["OpenAI", "Google", "Microsoft", "Forrester"]
  question.right         // ["Atlas", "Chrome", "Edge", "Research"]
);
// Result: "OpenAI → Research, Google → Chrome, Microsoft → Chrome, Forrester → Atlas"
```

---

## Before/After

| Before | After |
|--------|-------|
| `3, 1, 1, 0` | `OpenAI → Research, Google → Chrome, Microsoft → Chrome, Forrester → Atlas` |
| `0, 1, 2, 3` | `OpenAI → Atlas, Google → Chrome, Microsoft → Edge, Forrester → Research` |

---

## Edge Cases

| Case | Handling |
|------|----------|
| `left` or `right` is `null` | Fall back to showing raw indices |
| Question was deleted | `left`/`right` will be `null`, show indices |
| Index out of bounds | Show `[Unknown]` for that item |

```typescript
function safeGetRight(right: string[], idx: number): string {
  return right?.[idx] ?? "[Unknown]";
}
```
