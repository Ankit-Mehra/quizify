# Frontend Integration Guide: Structured Quiz Explanations

## 🎯 What Changed?

The quiz generation API now returns **structured explanations** with separate details for each answer option (for MCQ and fill-in-blank questions).

---

## 📊 New API Response Structure

### Before (Old Response):
```json
{
  "id": "uuid",
  "type": "multiple_choice",
  "question": "What is the powerhouse of the cell?",
  "correct_answer": "Mitochondria",
  "options": ["Mitochondria", "Nucleus", "Ribosome", "Chloroplast"],
  "explanation": "Mitochondria is correct because it produces ATP. The nucleus stores DNA but doesn't generate energy."
}
```

### After (New Response):
```json
{
  "id": "uuid",
  "type": "multiple_choice",
  "question": "What is the powerhouse of the cell?",
  "correct_answer": "Mitochondria",
  "options": ["Mitochondria", "Nucleus", "Ribosome", "Chloroplast"],
  "explanation": "Mitochondria is called the powerhouse of the cell because it produces ATP through cellular respiration.",
  "distractor_explanations": {
    "Nucleus": "The nucleus stores DNA and controls cell activities, but does not generate energy.",
    "Ribosome": "Ribosomes synthesize proteins, they don't produce energy.",
    "Chloroplast": "Chloroplasts are only in plant cells and produce glucose through photosynthesis, not ATP directly."
  }
}
```

**Key Differences:**
- ✅ `explanation` is now focused on WHY the correct answer is right
- ✅ `distractor_explanations` is a NEW optional field explaining why each wrong option is incorrect
- ✅ For **true/false** and **matching** questions, `distractor_explanations` will be `null` or omitted

---

## 🛠️ Implementation Options

You have **2 options** - choose based on your timeline and design preferences:

---

### Option 1: Simple (No Changes Required) ✅

**Just keep displaying `explanation` as you currently do.**

```tsx
// TypeScript - No schema changes needed
interface Question {
  id: string;
  type: string;
  question: string;
  explanation: string;  // <-- Just use this
  // ... other fields
}

// React Component - No changes
<div className="explanation">
  {question.explanation}
</div>
```

**Pros:**
- ✅ No code changes
- ✅ Works immediately
- ✅ Backward compatible

**Cons:**
- ❌ Users miss structured explanations for each option
- ❌ Less educational value

---

### Option 2: Robust (Recommended) 🚀

**Parse `distractor_explanations` and display them nicely.**

#### Step 1: Update TypeScript Schema

```typescript
// Add optional field to your Question interface
interface Question {
  id: string;
  type: 'multiple_choice' | 'fill_blank' | 'true_false' | 'matching';
  question: string;
  correct_answer: string | boolean | number[];
  options?: string[];
  explanation: string;
  distractor_explanations?: Record<string, string>;  // 👈 NEW FIELD
  // ... other fields
}
```

#### Step 2: Create UI Component

```tsx
// Example React Component
interface ExplanationProps {
  question: Question;
}

export function QuestionExplanation({ question }: ExplanationProps) {
  const hasDistractors = 
    question.distractor_explanations && 
    Object.keys(question.distractor_explanations).length > 0;

  return (
    <div className="explanation-container">
      {/* Main explanation - why correct answer is right */}
      <div className="main-explanation">
        <div className="explanation-header">
          <span className="icon">✅</span>
          <h4>Why this is correct:</h4>
        </div>
        <p>{question.explanation}</p>
      </div>

      {/* Distractor explanations - why wrong answers are wrong */}
      {hasDistractors && (
        <div className="distractor-section">
          <div className="explanation-header">
            <span className="icon">❌</span>
            <h4>Why other options are incorrect:</h4>
          </div>
          <ul className="distractor-list">
            {Object.entries(question.distractor_explanations!).map(([option, explanation]) => (
              <li key={option} className="distractor-item">
                <strong className="option-name">{option}:</strong>
                <span className="option-explanation">{explanation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

#### Step 3: Add CSS Styling (Example)

```css
.explanation-container {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  margin-top: 16px;
}

.main-explanation {
  margin-bottom: 20px;
}

.explanation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.explanation-header .icon {
  font-size: 20px;
}

.explanation-header h4 {
  margin: 0;
  color: #333;
  font-size: 16px;
}

.main-explanation p {
  margin: 0;
  color: #555;
  line-height: 1.6;
}

.distractor-section {
  border-top: 1px solid #dee2e6;
  padding-top: 16px;
}

.distractor-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.distractor-item {
  padding: 12px;
  margin-bottom: 8px;
  background: white;
  border-radius: 6px;
  border-left: 3px solid #dc3545;
}

.distractor-item:last-child {
  margin-bottom: 0;
}

.option-name {
  color: #dc3545;
  font-weight: 600;
  margin-right: 8px;
}

.option-explanation {
  color: #555;
  line-height: 1.6;
}
```

---

## 🎨 Visual Result (Option 2)

When rendered, it will look like this:

```
┌─────────────────────────────────────────────┐
│ ✅ Why this is correct:                     │
│                                             │
│ Mitochondria is called the powerhouse of   │
│ the cell because it produces ATP through   │
│ cellular respiration.                       │
│                                             │
├─────────────────────────────────────────────┤
│ ❌ Why other options are incorrect:         │
│                                             │
│ ┌───────────────────────────────────────┐  │
│ │ Nucleus: The nucleus stores DNA and   │  │
│ │ controls cell activities, but does    │  │
│ │ not generate energy.                  │  │
│ └───────────────────────────────────────┘  │
│                                             │
│ ┌───────────────────────────────────────┐  │
│ │ Ribosome: Ribosomes synthesize        │  │
│ │ proteins, they don't produce energy.  │  │
│ └───────────────────────────────────────┘  │
│                                             │
│ ┌───────────────────────────────────────┐  │
│ │ Chloroplast: Chloroplasts are only in │  │
│ │ plant cells and produce glucose       │  │
│ │ through photosynthesis, not ATP.      │  │
│ └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

---

## 📋 Question Type Behavior

| Question Type | Has `distractor_explanations`? | Notes |
|---------------|-------------------------------|-------|
| **Multiple Choice** | ✅ Yes | Explains each wrong option |
| **Fill-in-Blank** | ✅ Yes | Explains why other words don't fit |
| **True/False** | ❌ No | Binary choice, no distractors needed |
| **Matching** | ❌ No | Pairs structure, handled differently |

---

## 🧪 Testing Checklist

### For Both Options:
- [ ] Test MCQ questions display correctly
- [ ] Test fill-in-blank questions display correctly
- [ ] Test true/false questions (no distractors)
- [ ] Test matching questions (no distractors)
- [ ] Test when API returns `distractor_explanations: null`
- [ ] Test when API omits `distractor_explanations` field entirely

### For Option 2 Specifically:
- [ ] UI renders without errors when `distractor_explanations` is present
- [ ] UI renders without errors when `distractor_explanations` is missing
- [ ] Option names match exactly with the actual options in `question.options`
- [ ] Styling looks good on mobile and desktop
- [ ] Accessible (screen reader friendly)

---

## 🚀 Migration Path

### Phase 1: Backend Deployed (✅ Done)
- Backend now returns `distractor_explanations` field
- Backward compatible - existing frontend code works

### Phase 2: Frontend Decision (Your Choice)
- **Option 1**: Do nothing, keep using `explanation` only
- **Option 2**: Implement structured display (timeline: 1-2 days)

### Phase 3: Optional Enhancements
- Add collapsible sections (show/hide distractors)
- Add animations
- Add tooltips or "Learn more" buttons
- A/B test to measure impact on learning outcomes

---

## 📞 Questions?

- **Backend Changes**: See `PR_168_DESCRIPTION.md` for full details
- **API Contract**: All existing endpoints work the same, just added optional field
- **Testing**: Test data available in staging environment
- **Support**: Reach out in #quiz-generation Slack channel

**TL;DR: Backward compatible, no frontend changes required. But if you want better UX, add `distractor_explanations?: Record<string, string>` to your schema and render it nicely!**
