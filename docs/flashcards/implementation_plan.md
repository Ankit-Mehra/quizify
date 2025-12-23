# Flashcard Integration Implementation Plan

## Executive Summary
This document outlines the roadmap for integrating AI-generated flashcards into Quizify. Based on the research in `initial.md` and our current architecture, we will implement this feature by refactoring our existing monolithic handlers into modular services. This ensures that Flashcards, Quizzes, and future learning tools (e.g., Summaries, Mind Maps) share a common infrastructure for content ingestion, AI generation, and exporting.

## 🏗️ Architecture & Refactoring Strategy

To support Flashcards alongside Quizzes without code duplication, we will refactor the current `quiz_handlers.py` logic into reusable **Domain Services**.

### Current vs. Target Architecture

| Component | Current State | Target State (Refactored) |
|-----------|---------------|---------------------------|
| **Ingestion** | Scattered in `quiz_handlers.py` (PDF/Docx extraction, scraping) | **`ContentIngestionService`**: Unified entry point for Text, Files, and URLs. Returns standardized `Document` objects. |
| **Generation** | `openai_service.py` tightly coupled to Quiz types | **`AIGenerationService`**: Strategy pattern supporting `QuizGenerator` and `FlashcardGenerator` strategies. |
| **LLM Provider** | Hardcoded `openai_service.py` calls | **`LLMProviderFactory`**: Unified interface (`ILLMProvider`) allowing runtime switching between OpenAI, Gemini, and Groq. |
| **Storage** | `save_quiz_to_database` in `supabase_quiz.py` | **`LearningContentService`**: Unified storage for "Study Sets" which can contain Questions (Quiz) or Cards (Flashcards). |
| **Export** | `export_handler.py` with `BaseExporter` | **`ExportService`**: Enhanced to support "Deck" exports (Anki, PDF Flashcards) reusing the existing registry. |

---

## 🚀 Epics Breakdown

### Epic 1: Service Layer Refactoring (The Foundation)
**Goal**: Decouple content processing from quiz logic to allow reuse for flashcards.

- **1.1 Extract `ContentIngestionService`**
  - Move file parsing (PDF/DOCX/TXT) and URL scraping logic from `quiz_handlers.py` to `services/content/ingestion_service.py`.
  - **Output**: Standardized `IngestedContent` object (text, metadata, source_type).
  - *Benefit*: Flashcards can be generated from the exact same sources as quizzes.

- **1.2 Abstract `AIGenerationService`**
  - Refactor `openai_service.py` to accept a `GenerationStrategy`.
  - Create `FlashcardGenerationStrategy` that implements the specific prompting best practices from `initial.md` (atomic facts, Q&A format).
  - **Refactoring**: Rename `generate_quiz_async` to generic `generate_learning_content_async`.
- **1.3 Abstract `LLMProvider` Interface**
  - Create `services/llm/base.py` defining `ILLMProvider` (generate_json, generate_text).
  - Implement adapters: `OpenAIProvider`, `GeminiProvider`, `GroqProvider`.
  - **Configuration**: Allow switching provider via env vars or user preference (e.g., `LLM_PROVIDER=gemini`).
  - **Benefit**: Cost optimization and fallback redundancy.


### Epic 2: Flashcard Generation Engine (The AI)
**Goal**: Implement high-quality flashcard generation using LLMs.

- **2.1 Flashcard Prompt Engineering**
  - Implement `build_flashcard_prompt` in `services/ai_services/prompts.py`.
  - **Key Requirement**: Enforce "Atomic Facts" and "No Context Dependency" (e.g., avoid "According to the text...").
  - **Format**: JSON output `{"front": "...", "back": "..."}`.

- **2.2 Flashcard Generation Service**
  - Implement `generate_flashcards(text, count)` in `services/ai_services/flashcard_service.py`.
  - **Logic**: 
    - Calculate card count based on word count (~1 card per 100 words).
    - Chunking support for long documents (reusing `chunking_service.py`).

### Epic 3: Data Model & Storage (The Persistence)
**Goal**: Store flashcards efficiently, possibly reusing or extending existing tables.

- **3.1 Database Schema Updates**
  - **Option A (Reuse)**: Add `type = 'flashcard'` to `questions` table. Map `question` -> `front`, `explanation` -> `back`.
  - **Option B (New Table)**: Create `flashcards` table linked to a `deck_id`.
  - **Recommendation**: **Option A** is preferred for simplicity. A "Quiz" becomes a generic "Study Set" that can be `mode='quiz'` or `mode='flashcards'`.

- **3.2 API Endpoints**
  - `POST /api/flashcards/generate`: Triggers generation.
  - `GET /api/flashcards/{set_id}`: Retrieves cards.
  - `PUT /api/flashcards/{card_id}`: Edit front/back (crucial for user curation).

### Epic 4: Study & Review Experience (Frontend & API)
**Goal**: Interactive study interface.

- **4.1 Review API**
  - Endpoints to track "Known" vs "Unknown" status for session-based review.
  - *Future*: Store spaced repetition metadata (box number, next review date).

- **4.2 Frontend Components**
  - **FlashcardComponent**: UI with "Flip" animation.
  - **DeckView**: Navigation (Next/Prev), Progress bar.
  - **Edit Mode**: Allow users to modify AI-generated cards (correcting hallucinations).

### Epic 5: Export & Interoperability
**Goal**: Leverage existing export infrastructure for Flashcards.

- **5.1 Enhance `CsvAnkiExporter`**
  - The existing `services/exporters/csv_anki_exporter.py` is already well-positioned.
  - **Update**: Ensure it handles the `flashcard` type explicitly (Front/Back mapping).
  - **Feature**: Allow exporting a "Quiz" as "Flashcards" (automatically converting MCQ Question -> Front, Correct Answer -> Back).

- **5.2 PDF Flashcard Exporter**
  - Create `services/exporters/pdf_flashcard_exporter.py`.
  - **Layout**: 2-column layout (Questions left, Answers right) or Page-break format (Question page, Answer page) for printing.

---

## 🛠️ Technical Specifications & Code Mapping

### 1. New Schemas (`schemas/flashcard.py`)
```python
class FlashcardBase(BaseModel):
    front: str = Field(..., description="The question or prompt")
    back: str = Field(..., description="The answer or response")
    
class Flashcard(FlashcardBase):
    id: UUID
    deck_id: UUID
    # Metadata for Spaced Repetition (Future proofing)
    status: Literal["new", "learning", "review", "mastered"] = "new"
```

### 2. Prompt Engineering (`services/ai_services/prompts.py`)
*Based on research:*
```python
def build_flashcard_prompt(text: str, num_cards: int) -> str:
    return f"""
    Create {num_cards} concise flashcards from the text.
    Format: JSON {{ "cards": [ {{ "front": "...", "back": "..." }} ] }}
    
    Rules:
    1. Atomic: One fact per card.
    2. Self-contained: No "According to the text".
    3. Brevity: Front/Back under 15 words each.
    4. Types: Mix definitions, "why" questions, and cloze deletions (fill-in-blank).
    
    Text: {text}
    """
```

### 3. Reusing `CsvAnkiExporter`
The current `CsvAnkiExporter` iterates over `quiz_data.questions`. We can simply map our new `Flashcard` objects to the `ExportQuestion` interface or update the exporter to handle `Flashcard` objects directly.

``# 4. LLM Provider Abstraction (`services/llm/`)
```python
class AnalyticsContext(BaseModel):
    user_id: str
    trace_id: str
    properties: Dict[str, Any] = {}

class ILLMProvider(ABC):
    @abstractmethod
    async def generate_structured_output(
        self, 
        prompt: str, 
        schema: Type[BaseModel],
        analytics: Optional[AnalyticsContext] = None
    ) -> BaseModel:
        pass

class OpenAIProvider(ILLMProvider):
    def __init__(self):
        # Initialize PostHog-wrapped client
        self.client = get_openai_client() 

    async def generate_structured_output(self, prompt, schema, analytics):
        # Pass analytics context to PostHog wrapper
        kwargs = {}
        if analytics:
            kwargs = _build_posthog_kwargs(analytics.user_id, analytics.trace_id, analytics.properties)
        
        return await self.client.chat.completions.create(..., **kwargs)

class GeminiProvider(ILLMProvider):
    def __init__(self):
        self.client = genai.Client(...)
        self.posthog = get_posthog_client()

    async def generate_structured_output(self, prompt, schema, analytics):
        start = time.time()
        response = await self.client.models.generate_content(...)
        
        # Manual PostHog tracking for non-OpenAI providers
        if self.posthog and analytics:
            self.posthog.capture(
                analytics.user_id,
                "$ai_generation",
                properties={
                    "$ai_provider": "gemini",
                    "$ai_model": "gemini-1.5-flash",
                    "$ai_trace_id": analytics.trace_id,
                    "latency": time.time() - start,
                    **analytics.properties
                }
            )
        return response

class LLMFactory:
    @staticmethod
    def get_provider(provider_name: str = "openai") -> ILLMProvider:
        if provider_name == "gemini": return GeminiProvider()
        if provider_name == "groq": return GroqProvider()
        return OpenAIProvider()
```

##`python
# services/exporters/csv_anki_exporter.py
def _flashcard_to_cards(self, card: Flashcard) -> List[List[str]]:
    return [[card.front, card.back]]
```

## 📅 Phasing

1.  **Phase 1 (MVP)**: Service Refactoring + Basic Generation + JSON/Anki Export.
2.  **Phase 2 (UI)**: Web Interface for reviewing and editing cards.
3.  **Phase 3 (Advanced)**: Spaced Repetition logic (Leitner system) + PDF Export.
