# Quiz Generation Data Flow

This document provides comprehensive Mermaid diagrams showing how data flows from the frontend through quiz generation for both Standard and Enhanced modes.

## Table of Contents
1. [High-Level Overview](#high-level-overview)
2. [Frontend to Backend Flow](#frontend-to-backend-flow)
3. [Standard Mode Pipeline](#standard-mode-pipeline)
4. [Enhanced Mode Pipeline](#enhanced-mode-pipeline)
5. [Service Interactions](#service-interactions)
6. [Database Schema](#database-schema)

---

## High-Level Overview

```mermaid
flowchart TB
    subgraph Frontend["Frontend (React/Next.js)"]
        UI[User Interface]
        Auth[Auth Context]
        PostHogFE[PostHog Identify]
    end
    
    subgraph Backend["Backend (FastAPI)"]
        API[API Routes]
        Handlers[Quiz Handlers]
        
        subgraph Modes["Generation Modes"]
            Standard[Standard Mode]
            Enhanced[Enhanced/RAG Mode]
        end
        
        subgraph Services["AI Services"]
            Chunking[Chunking Service]
            Ingestion[Ingestion Service]
            Concepts[Concept Extraction]
            Orchestration[Orchestration Service]
            Context[Context Service]
            Explanation[Explanation Service]
        end
    end
    
    subgraph External["External Services"]
        OpenAI[OpenAI API]
        Supabase[(Supabase)]
        PostHogBE[PostHog Analytics]
    end
    
    UI --> Auth
    Auth --> PostHogFE
    PostHogFE -->|identify user| PostHogBE
    UI -->|HTTP Request| API
    API --> Handlers
    Handlers --> Standard
    Handlers --> Enhanced
    Standard --> Chunking
    Enhanced --> Ingestion
    Enhanced --> Concepts
    Enhanced --> Orchestration
    Orchestration --> Context
    Orchestration --> Explanation
    
    Chunking --> OpenAI
    Ingestion --> OpenAI
    Concepts --> OpenAI
    Orchestration --> OpenAI
    Explanation --> OpenAI
    
    OpenAI -.->|PostHog wrapped| PostHogBE
    
    Handlers --> Supabase
```

---

## Frontend to Backend Flow

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Frontend
    participant PostHog as PostHog (Frontend)
    participant API as FastAPI Router
    participant Auth as Auth Dependency
    participant Handler as Quiz Handler
    participant DB as Supabase
    
    User->>Frontend: Login
    Frontend->>PostHog: posthog.identify(user_id, {email})
    Note over PostHog: Links user_id to email
    
    User->>Frontend: Submit Quiz Request
    Note over Frontend: Content: text/file/URL<br/>Title, num_questions, mode
    
    Frontend->>API: POST /api/quiz/generate/{type}
    Note over API: Authorization: Bearer JWT
    
    API->>Auth: get_current_user_id()
    Auth->>DB: Validate JWT
    DB-->>Auth: User ID
    Auth-->>API: user_id, user_token
    
    API->>Handler: Call appropriate handler
    Note over Handler: generate_quiz_from_text()<br/>generate_quiz_from_file_openai()<br/>generate_quiz_from_url()
    
    Handler->>DB: validate_user_quota(user_id)
    Note over DB: Check user_tier_info view
    
    alt Quota Exceeded
        DB-->>Handler: quota_exceeded: true
        Handler-->>API: HTTPException 403
        API-->>Frontend: 403 Forbidden
    else Quota OK
        DB-->>Handler: quota_exceeded: false
        Handler->>Handler: Route to generation mode
    end
```

---

## Standard Mode Pipeline

```mermaid
flowchart TB
    subgraph Input["Input Processing"]
        Request[EnhancedTextQuizRequest]
        Validate[Validate Request]
        QuotaCheck[Check User Quota]
    end
    
    subgraph StandardMode["Standard Mode - Fast Generation"]
        Chunk[Smart Chunk Text]
        Distribute[Distribute Questions per Type]
        
        subgraph ParallelLLM["Parallel LLM Calls"]
            LLM1[Generate MCQ]
            LLM2[Generate T/F]
            LLM3[Generate Fill Blank]
            LLM4[Generate Matching]
        end
        
        Merge[Merge Results]
    end
    
    subgraph Output["Output Processing"]
        Convert[Convert to EnhancedQuestion]
        SaveDB[(Save to Database)]
        Response[EnhancedQuizGenerationResponse]
    end
    
    Request --> Validate
    Validate --> QuotaCheck
    QuotaCheck --> Chunk
    Chunk --> Distribute
    Distribute --> LLM1
    Distribute --> LLM2
    Distribute --> LLM3
    Distribute --> LLM4
    LLM1 --> Merge
    LLM2 --> Merge
    LLM3 --> Merge
    LLM4 --> Merge
    Merge --> Convert
    Convert --> SaveDB
    SaveDB --> Response
```

### Standard Mode Detailed Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Handler as generate_quiz_rag_async
    participant Standard as _generate_standard_mode
    participant Chunking as chunking_service
    participant OpenAI as OpenAI API
    participant PostHog as PostHog (Backend)
    participant DB as Supabase
    
    Handler->>Standard: mode="standard"
    
    Standard->>Chunking: generate_quizzes_single_async()
    
    Chunking->>Chunking: smart_chunk_text()
    Note over Chunking: Split text into optimal chunks<br/>based on token limits
    
    Chunking->>Chunking: Distribute questions per type
    Note over Chunking: MCQ: 3, T/F: 2, etc.
    
    par Parallel LLM Calls
        Chunking->>OpenAI: Generate MCQ questions
        Chunking->>OpenAI: Generate T/F questions
        Chunking->>OpenAI: Generate Fill-Blank
        Chunking->>OpenAI: Generate Matching
    end
    
    OpenAI-->>PostHog: Track LLM call (via wrapper)
    Note over PostHog: posthog_distinct_id = user email<br/>posthog_trace_id = trace_id
    
    OpenAI-->>Chunking: Question responses
    
    Chunking->>Chunking: Parse & validate JSON
    Chunking-->>Standard: List[Question]
    
    Standard->>DB: save_quiz_to_database()
    Note over DB: Insert quiz + questions<br/>Track content_source
    
    Standard->>Standard: Convert to EnhancedQuestion
    Note over Standard: Add default bloom_level=UNDERSTAND<br/>Add default difficulty=MEDIUM
    
    Standard-->>Handler: EnhancedQuizGenerationResponse
```

---

## Enhanced Mode Pipeline

```mermaid
flowchart TB
    subgraph Input["Input Processing"]
        Request[EnhancedTextQuizRequest]
        Validate[Validate Request]
        QuotaCheck[Check User Quota]
    end
    
    subgraph RAG["RAG Pipeline"]
        subgraph Ingestion["1. Ingestion"]
            CreateDoc[Create Document Record]
            LlamaChunk[LlamaIndex SentenceSplitter]
            Embed1[Generate Embeddings]
            SaveChunks[(Save Chunks + Vectors)]
        end
        
        subgraph Extraction["2. Concept Extraction"]
            direction TB
            ParallelExtract[Parallel Chunk Processing]
            LLMExtract[GPT-4o-mini Extract Concepts]
            Embed2[Generate Concept Embeddings]
            SaveConcepts[(Save Concepts)]
        end
        
        subgraph Selection["3. Concept Selection"]
            RankConcepts[Rank by Relevance]
            SelectTop[Select Top N Concepts]
            AssignTypes[Assign Question Types]
            AssignBloom[Assign Bloom Levels]
        end
        
        subgraph Generation["4. Question Generation"]
            direction TB
            ParallelGen[Parallel Question Gen]
            GetContext[Context Service]
            LLMGen[GPT-4o Generate Question]
            VerifyExplain[Verify + Explain]
        end
    end
    
    subgraph Output["Output Processing"]
        BuildQuestions[Build EnhancedQuestions]
        SaveDB[(Save to Database)]
        Response[EnhancedQuizGenerationResponse]
    end
    
    Request --> Validate
    Validate --> QuotaCheck
    QuotaCheck --> CreateDoc
    CreateDoc --> LlamaChunk
    LlamaChunk --> Embed1
    Embed1 --> SaveChunks
    SaveChunks --> ParallelExtract
    ParallelExtract --> LLMExtract
    LLMExtract --> Embed2
    Embed2 --> SaveConcepts
    SaveConcepts --> RankConcepts
    RankConcepts --> SelectTop
    SelectTop --> AssignTypes
    AssignTypes --> AssignBloom
    AssignBloom --> ParallelGen
    ParallelGen --> GetContext
    GetContext --> LLMGen
    LLMGen --> VerifyExplain
    VerifyExplain --> BuildQuestions
    BuildQuestions --> SaveDB
    SaveDB --> Response
```

### Enhanced Mode Detailed Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Handler as _generate_enhanced_mode
    participant Ingestion as IngestionService
    participant Concept as ConceptExtractionService
    participant Orch as OrchestrationService
    participant Context as ContextService
    participant Explain as ExplanationService
    participant OpenAI as OpenAI API
    participant PostHog as PostHog
    participant DB as Supabase
    
    Note over Handler: trace_id = uuid4()
    
    rect rgb(200, 230, 255)
        Note over Handler,DB: Phase 1: Ingestion
        Handler->>Ingestion: ingest_content()
        Ingestion->>DB: create_document()
        Ingestion->>Ingestion: SentenceSplitter.get_nodes()
        Note over Ingestion: chunk_size=500, overlap=50
        
        Ingestion->>OpenAI: embeddings.create()
        Note over OpenAI: text-embedding-3-small<br/>dimensions=1536
        OpenAI-->>PostHog: Track embedding call
        OpenAI-->>Ingestion: embeddings[]
        
        Ingestion->>DB: create_chunks(chunks + vectors)
        Ingestion-->>Handler: {document_id, chunks[]}
    end
    
    rect rgb(255, 230, 200)
        Note over Handler,DB: Phase 2: Concept Extraction
        Handler->>Concept: extract_concepts()
        
        par Parallel Chunk Processing (10 concurrent)
            Concept->>OpenAI: Extract concepts from chunk 1
            Concept->>OpenAI: Extract concepts from chunk 2
            Concept->>OpenAI: Extract concepts from chunk N
        end
        Note over OpenAI: GPT-4o-mini<br/>JSON response
        OpenAI-->>PostHog: Track extraction calls
        
        Concept->>Concept: Deduplicate concepts
        Concept->>OpenAI: embeddings.create(concept names)
        Concept->>DB: create_concepts()
        Concept-->>Handler: concepts[]
    end
    
    rect rgb(230, 255, 200)
        Note over Handler,DB: Phase 3: Question Generation
        Handler->>Handler: _select_and_assign_concepts()
        Note over Handler: Sort by relevance<br/>Assign question types<br/>Assign Bloom levels
        
        Handler->>Orch: generate_question_for_concept() × N
        
        par Parallel Question Generation
            Orch->>Context: get_context_for_concept()
            Context->>DB: get_chunk()
            alt Enhanced Context Mode
                Context->>DB: match_chunks(similarity)
            end
            Context-->>Orch: context string
            
            Orch->>OpenAI: Generate question (GPT-4o)
            OpenAI-->>PostHog: Track generation call
            OpenAI-->>Orch: question JSON
            
            Orch->>Explain: verify_and_explain()
            Explain->>OpenAI: Verify + Explain (GPT-4o-mini)
            Note over OpenAI: Single combined call<br/>50% faster than separate
            OpenAI-->>PostHog: Track verify_explain call
            OpenAI-->>Explain: {is_accurate, explanation}
            Explain-->>Orch: (valid, confidence, issues, explanation)
        end
        
        Orch-->>Handler: valid_questions[]
    end
    
    rect rgb(255, 200, 230)
        Note over Handler,DB: Phase 4: Save & Return
        Handler->>Handler: _build_enhanced_questions()
        Handler->>DB: save_quiz_to_database()
        Handler-->>Handler: EnhancedQuizGenerationResponse
    end
```

---

## Service Interactions

```mermaid
flowchart LR
    subgraph Handlers
        QH[quiz_handlers.py]
    end
    
    subgraph AIServices["AI Services"]
        CS[chunking_service.py]
        IS[ingestion_service.py]
        CES[concept_extraction_service.py]
        OS[orchestration_service.py]
        CtxS[context_service.py]
        ES[explanation_service.py]
        OAI[openai_service.py]
    end
    
    subgraph DBServices["DB Services"]
        SQ[supabase_quiz.py]
        SC[supabase_chunks.py]
        SD[supabase_documents.py]
        SCon[supabase_concepts.py]
        SLA[supabase_llm_analytics.py]
    end
    
    subgraph External
        OpenAI[(OpenAI API)]
        Supabase[(Supabase)]
        PostHog[PostHog]
    end
    
    QH -->|Standard| CS
    QH -->|Enhanced| IS
    QH -->|Enhanced| CES
    QH -->|Enhanced| OS
    
    IS --> OAI
    CES --> OAI
    OS --> OAI
    OS --> CtxS
    OS --> ES
    ES --> OAI
    CS --> OAI
    
    CtxS --> SC
    IS --> SD
    IS --> SC
    CES --> SCon
    QH --> SQ
    
    OAI --> OpenAI
    OAI -.->|wrapped client| PostHog
    
    SD --> Supabase
    SC --> Supabase
    SCon --> Supabase
    SQ --> Supabase
    SLA --> Supabase
```

---

## Database Schema

```mermaid
erDiagram
    auth_users ||--o{ profiles : has
    auth_users ||--o{ quizzes : creates
    auth_users ||--o{ user_files : uploads
    auth_users ||--o{ documents : owns
    
    quizzes ||--|{ questions : contains
    quizzes ||--o{ quiz_metadata : has
    quizzes ||--o{ submissions : receives
    
    documents ||--|{ chunks : split_into
    chunks ||--o{ concepts : extracted_from
    
    user_files {
        uuid id PK
        uuid user_id FK
        string storage_path
        string original_filename
        string file_type
        int file_size_bytes
        timestamp created_at
    }
    
    quizzes {
        uuid id PK
        string title
        uuid created_by FK
        string content_source_type
        string content_source_reference
        timestamp created_at
    }
    
    questions {
        uuid id PK
        uuid quiz_id FK
        string type
        text question
        jsonb options
        jsonb left
        jsonb right
        text correct_answer
        text explanation
        string bloom_level
        string difficulty
        uuid concept_id FK
        uuid chunk_id FK
        float confidence_score
    }
    
    documents {
        uuid id PK
        uuid user_id FK
        string title
        string source_type
        string source_reference
        int token_count
        timestamp created_at
    }
    
    chunks {
        uuid id PK
        uuid document_id FK
        int chunk_index
        text content
        int token_count
        vector embedding
    }
    
    concepts {
        uuid id PK
        uuid document_id FK
        uuid chunk_id FK
        string name
        string concept_type
        float relevance_score
        text source_text
        vector embedding
    }
    
    profiles {
        uuid id PK
        string account_tier
        string name
        timestamp created_at
    }
    
    llm_analytics {
        uuid id PK
        uuid user_id FK
        string trace_id
        string call_type
        string model
        int input_tokens
        int output_tokens
        int latency_ms
        float cost_usd
        jsonb metadata
        timestamp created_at
    }
```

---

## LLM Calls Summary

### Standard Mode
| Step | Model | Purpose | Tokens (avg) |
|------|-------|---------|--------------|
| 1 | gpt-4o | Generate questions (parallel per type) | ~2000 in, ~500 out |

**Total: 1 LLM call per question type** (~4 calls for mixed)

### Enhanced Mode
| Step | Model | Purpose | Tokens (avg) |
|------|-------|---------|--------------|
| 1 | text-embedding-3-small | Embed chunks | ~500 per chunk |
| 2 | gpt-4o-mini | Extract concepts (per chunk) | ~600 in, ~200 out |
| 3 | text-embedding-3-small | Embed concept names | ~50 per concept |
| 4 | gpt-4o | Generate question (per concept) | ~800 in, ~300 out |
| 5 | gpt-4o-mini | Verify + Explain (per question) | ~400 in, ~150 out |

**Total: 2-3 LLM calls per question** (Generation + Verify/Explain combined)

---

## PostHog Analytics Flow

```mermaid
sequenceDiagram
    participant Frontend
    participant PostHog as PostHog Cloud
    participant Backend
    participant OpenAI
    
    Note over Frontend,PostHog: User Identification
    Frontend->>PostHog: posthog.identify(user_id, {email})
    Note over PostHog: Creates/updates person profile<br/>Links user_id to email
    
    Note over Backend,OpenAI: LLM Call Tracking
    Backend->>OpenAI: API call with posthog kwargs
    Note over Backend: posthog_distinct_id = email (cached lookup)<br/>posthog_trace_id = trace_id
    
    OpenAI-->>PostHog: Auto-track via wrapped client
    Note over PostHog: Records: model, tokens, latency<br/>Groups by distinct_id (email)
    
    Note over PostHog: Result: All LLM calls<br/>attributed to user email
```

---

## Input Sources

```mermaid
flowchart TB
    subgraph Sources["Content Sources"]
        Text["/quiz/generate/text"]
        File["/quiz/generate/file"]
        FileID["/quiz/generate/{file_id}"]
        URL["/quiz/generate/url"]
    end
    
    subgraph Processing["Content Processing"]
        TextP[Direct text input]
        FileP[extract_text_from_pdf/docx/txt]
        FileIDP[parse_file_from_supabase]
        URLP[scrape_content via Playwright]
    end
    
    subgraph Unified["Unified Generation"]
        Request[EnhancedTextQuizRequest]
        RAG[generate_quiz_rag_async]
    end
    
    Text --> TextP
    File --> FileP
    FileID --> FileIDP
    URL --> URLP
    
    TextP --> Request
    FileP --> Request
    FileIDP --> Request
    URLP --> Request
    
    Request --> RAG
    
    RAG -->|mode=standard| Standard[Standard Mode]
    RAG -->|mode=enhanced| Enhanced[Enhanced Mode]
```

---

## Error Handling

```mermaid
flowchart TB
    subgraph Errors["Error Types"]
        Auth[401 Unauthorized]
        Quota[403 Quota Exceeded]
        NotFound[404 Not Found]
        BadInput[400 Bad Request]
        Server[500 Server Error]
    end
    
    subgraph Checks["Validation Points"]
        JWTCheck[JWT Validation]
        QuotaCheck[Quota Validation]
        FileCheck[File Existence]
        ContentCheck[Content Length]
        GenerateCheck[Generation Errors]
    end
    
    JWTCheck -->|Invalid| Auth
    QuotaCheck -->|Exceeded| Quota
    FileCheck -->|Missing| NotFound
    ContentCheck -->|Too Short| BadInput
    GenerateCheck -->|Failed| Server
```

---

## Summary

| Aspect | Standard Mode | Enhanced Mode |
|--------|--------------|---------------|
| **Speed** | Fast (~5-10s) | Slower (~30-60s) |
| **LLM Calls** | 1 per type (~4 total) | 2-3 per question |
| **Context** | Full text chunked | RAG-retrieved context |
| **Bloom Levels** | Default (UNDERSTAND) | Distributed (all 6) |
| **Difficulty** | Default (MEDIUM) | Distributed (easy/medium/hard) |
| **Verification** | None | GPT-4o-mini verify+explain |
| **Cost** | ~$0.01-0.02 | ~$0.05-0.15 |
| **Quality** | Good | Higher (verified) |
