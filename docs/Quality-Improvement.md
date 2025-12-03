Here is a **detailed, production-grade implementation plan** for high-quality quiz generation in **Quizify**, using:

* ✅ `LlamaIndex` for chunking, embedding, RAG
* ✅ `Supabase` for both **vector store** and **relational DB**
* ✅ `FastAPI` as backend framework
* ✅ `OpenAI` (GPT-4 Turbo or GPT-4o) for LLM generation

This implementation plan breaks down all modules, their responsibilities, required libraries, database integration, and how they link to one another.

---

# 🧱 MODULE BREAKDOWN (Backed by Supabase + LlamaIndex)

---

## **1. Ingestion & Preprocessing Module**

### 📌 Responsibilities:

* Handle text, PDF, URL input
* Clean and chunk input into LlamaIndex nodes
* Embed and store in Supabase (vector store)

### 🧩 Libraries:

* `LlamaIndex`
* `PyMuPDF` (`fitz`) for PDF
* `trafilatura` or `readability-lxml` for URL scraping
* `aiofiles`, `python-multipart` (for file uploads via FastAPI)

### 🛠 Implementation Steps:

```python
# Use LlamaIndex ingestion + Supabase integration
from llama_index.core import SimpleDirectoryReader, ServiceContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.supabase import SupabaseVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding

# 1. Read content
docs = SimpleDirectoryReader("input_docs/").load_data()

# 2. Chunk
parser = SentenceSplitter(chunk_size=512)
nodes = parser.get_nodes_from_documents(docs)

# 3. Attach metadata
for node in nodes:
    node.metadata = {"source": "file_name.pdf"}

# 4. Set up Supabase vector store
supabase_store = SupabaseVectorStore(postgres_connection_string=...)

index = VectorStoreIndex(nodes, vector_store=supabase_store)
index.storage_context.persist()
```

### ✅ Output:

* Embeddings and metadata stored in Supabase vector table
* Document info in `documents` table for tracking

---

## **2. Concept & Topic Extraction Module**

### 📌 Responsibilities:

* Extract semantic key concepts, entities, themes
* Store in a `concepts` table (relational)
* Link each to chunk_ids / document_ids

### 🧩 Libraries:

* `spaCy` + pretrained NER model
* `KeyBERT` for embedding-based keyword extraction
* `LlamaIndex SummaryNodeParser` (optional)

### 🛠 Steps:

```python
from keybert import KeyBERT
from spacy import load

nlp = load("en_core_web_sm")
kw_model = KeyBERT()

def extract_concepts(text):
    doc = nlp(text)
    entities = [ent.text for ent in doc.ents]
    keywords = kw_model.extract_keywords(text, keyphrase_ngram_range=(1, 2), stop_words='english')
    return set(entities + [kw[0] for kw in keywords])
```

### ✅ Output:

* Insert to `concepts` table with:

  * `concept`, `type`, `chunk_id`, `doc_id`, `embedding`, `relevance_score`

---

## **3. Quiz Generation Module**

### 📌 Responsibilities:

* For each concept (or chunk), generate a question with distractors
* Use prompt chaining: concept → question → distractors → explanation

### 🧩 Libraries:

* `OpenAI` GPT-4 Turbo / GPT-4o via `openai` SDK
* `asyncio.gather` to parallelize generation

### 🛠 Prompt Design:

```python
PROMPT = """
Given the following concept and passage, generate a multiple-choice question.

Concept: {concept}
Passage: {chunk_text}

- Ensure Bloom Level: {bloom_level}
- Provide 1 correct answer + 3 plausible distractors
- Include an answer explanation
"""
```

### 🛠 FastAPI Endpoint:

```python
@app.post("/generate-quiz/")
async def generate_quiz(request: QuizRequest):
    concepts = get_concepts(request.document_id)
    tasks = [generate_question(concept) for concept in concepts]
    results = await asyncio.gather(*tasks)
    return results
```

### ✅ Output:

* Store output in `questions` table:

  * `question_text`, `choices`, `correct_answer`, `explanation`, `concept_id`, `difficulty`, `bloom_level`

---

## **4. Explanation & Postprocessing Module**

### 📌 Responsibilities:

* Generate clear answer explanations (why correct, why distractors are wrong)
* Run basic fact check via RAG over vector store

### 🧩 Tools:

* Use LLM + Retrieval from LlamaIndex
* Use OpenAI Moderation API for hallucination/inappropriate content

```python
from llama_index.core.query_engine import RetrieverQueryEngine

query_engine = index.as_query_engine()
response = query_engine.query(f"What evidence supports this answer to: {question}?")
```

---

## **5. Bloom & Difficulty Classification Module**

### 📌 Responsibilities:

* Classify question into Bloom’s taxonomy
* Assign difficulty level (Easy/Medium/Hard)

### 🧩 Tools:

* OpenAI zero-shot classification or fine-tuned LLM
* Optionally store classification prompt results for traceability

```python
CLASSIFY_PROMPT = """
Classify the following question into a Bloom level and difficulty score.

Question: {question}
"""

# Result → {bloom_level: "Analyze", difficulty: "Medium"}
```

---

## **6. Adaptive Personalization Engine**

### 📌 Responsibilities:

* Model user learning profile (per topic, per Bloom level)
* Adapt quiz flow accordingly (future scope)
* Reuse stored embeddings and metadata

### 🧩 DB:

* `user_profiles` table → {user_id, concept_scores, mastery_level}
* `quiz_attempts` → track per-question accuracy and time

---

## **7. FastAPI + Supabase Integration Plan**

### 📂 Backend Layout

```
app/
├── api/
│   ├── ingest.py
│   ├── generate.py
│   ├── classify.py
│   ├── user.py
├── core/
│   ├── embeddings.py
│   ├── prompts.py
│   ├── llm.py
│   ├── concept_extract.py
├── db/
│   ├── supabase_client.py
│   ├── schema.sql
```

### 🧑‍💻 Supabase Tables

| Table           | Purpose                                      |
| --------------- | -------------------------------------------- |
| `documents`     | File metadata (title, uploader, token count) |
| `chunks`        | ID, text, embedding, doc_id                  |
| `concepts`      | Concept, type, relevance, linked chunk_id    |
| `questions`     | Full generated question object               |
| `quiz_attempts` | User performance per question                |
| `user_profiles` | Learner model per concept/topic              |

---

# ✅ END-TO-END FLOW OVERVIEW

1. **User uploads input** (text, PDF, or URL)
2. → Backend ingests & stores in Supabase vector DB
3. → Concept extraction runs over chunks
4. → LLM generates questions for selected concepts (or balanced coverage)
5. → Distractors + Explanation + Bloom tagging applied
6. → Final quiz stored and shown to frontend
7. (Later) → Adaptive engine uses user data to personalize next quizzes

---

Would you like me to:

* Scaffold this as a starter GitHub repo structure?
* Write the Supabase table DDLs?
* Build one module first (e.g. ingestion + chunking + Supabase insert)?


### for Quiz Generation Module do,nt we need a LLM orchestrator like llamindex ?? if yes updated the above plan with LLM orchestration layer

Yes — **you’re absolutely right**. For a structured, scalable, and easily maintainable quiz generation pipeline, you *should* absolutely use an **LLM orchestration layer**, especially since you’re using **LlamaIndex** throughout your stack.

LlamaIndex's **`LLMPredictor`**, **`PromptTemplate`**, and **`ResponseSynthesizer`** modules are purpose-built to manage multi-step prompting, integrate retrieval, inject metadata, and maintain consistent workflows.

---

### ✅ Here’s the updated and improved Quiz Generation Module:

We’ll replace manual prompting + raw asyncio with a **modular orchestration pipeline** using **LlamaIndex agents + service context**.

---

# 🔁 Updated: Quiz Generation Module (LLM-Orchestrated via LlamaIndex)

---

## 🔁 Module Responsibilities

| Sub-Task                         | Method via LlamaIndex                 |
| -------------------------------- | ------------------------------------- |
| Generate question from concept   | `LLMChainExtractor`, `PromptTemplate` |
| Generate distractors             | Custom post-processing callback       |
| Generate explanations            | `ResponseSynthesizer`                 |
| Chain multi-step LLM calls       | `LLMRouter` or `QueryEngineTool`      |
| Inject metadata (bloom, concept) | via `MetadataMode.EMBED`              |

---

## 🧰 Libraries and Interfaces Used

* `llama_index.llms.OpenAI`
* `PromptTemplate`, `LLMPredictor`, `ServiceContext`
* `ResponseSynthesizer` (for explanations)
* `ToolRetrieverQueryEngine` or `Custom Query Engines`

---

## 🛠️ Implementation Breakdown

### Step 1: Define Prompt Templates

```python
from llama_index.core.prompts import PromptTemplate

QUESTION_PROMPT = PromptTemplate(
    "Based on the following concept and passage, create a Bloom-level {level} MCQ.\n\n"
    "Concept: {concept}\n\n"
    "Passage:\n{context_str}\n\n"
    "Generate:\n- Question\n- 1 correct answer\n- 3 plausible distractors"
)
```

---

### Step 2: Set Up LLM + Context

```python
from llama_index.llms import OpenAI
from llama_index.core import ServiceContext

llm = OpenAI(model="gpt-4", temperature=0.7)
service_context = ServiceContext.from_defaults(llm=llm)
```

---

### Step 3: Attach to a Query Engine

Use either:

* A **retriever** for concept-related chunks
* Or iterate manually over your concept list

```python
from llama_index.core.query_engine import CustomQueryEngine

class QuizEngine(CustomQueryEngine):
    def __init__(self, prompt, service_context):
        self.prompt = prompt
        self.service_context = service_context

    def query(self, input):
        context = input["chunk_text"]
        concept = input["concept"]
        bloom_level = input.get("bloom_level", "Understand")
        formatted = self.prompt.format(
            concept=concept,
            level=bloom_level,
            context_str=context
        )
        return self.service_context.llm.complete(formatted)
```

---

### Step 4: Parallelize with Orchestration

Instead of `asyncio.gather()`, now use LlamaIndex’s **tool orchestration layer** (or batch through Python threading):

```python
# Loop over extracted concepts
results = []
for concept in concepts:
    top_chunks = vector_index.query(concept.name, similarity_top_k=2)
    for chunk in top_chunks:
        result = quiz_engine.query({
            "concept": concept.name,
            "chunk_text": chunk.text,
            "bloom_level": concept.bloom_hint
        })
        results.append(result)
```

---

### Step 5: Postprocess + Save

Use `ResponseSynthesizer` for answer explanations:

```python
from llama_index.core.response_synthesizers import get_response_synthesizer

explanation_prompt = PromptTemplate("Explain why the correct answer is right and the distractors are wrong.\n\n{context_str}")
synthesizer = get_response_synthesizer(prompt=explanation_prompt, service_context=service_context)

for q in results:
    explanation = synthesizer.synthesize([q.source_node])
```

---

## ✅ Final Output to Supabase

Save everything as a complete `question` object:

```json
{
  "question_text": "...",
  "correct_answer": "...",
  "distractors": ["...", "...", "..."],
  "explanation": "...",
  "concept_id": "uuid",
  "chunk_id": "uuid",
  "bloom_level": "Understand",
  "difficulty": "Medium"
}
```

---

## 💡 Why This Is Better than Raw Prompting

| Feature                      | Manual Prompts | LlamaIndex Orchestration   |
| ---------------------------- | -------------- | -------------------------- |
| Multi-step chaining          | ❌              | ✅                          |
| RAG-ready prompt scaffolding | ❌              | ✅                          |
| Metadata embedding           | Manual         | Native via LlamaIndex      |
| LLM swapping/config          | Manual         | Central via ServiceContext |
| Easy prompt reuse            | ❌              | ✅ with PromptTemplate      |

---

## 🧱 Updated Modules Map (Additions)

| Module                             | Tool / Library                                                     | Notes                                         |
| ---------------------------------- | ------------------------------------------------------------------ | --------------------------------------------- |
| Quiz Generation (LLM-Orchestrated) | `LlamaIndex.PromptTemplate`, `ServiceContext`, `CustomQueryEngine` | Replaces raw asyncio                          |
| Explanation Generator              | `ResponseSynthesizer`                                              | Auto-infers explanation from question context |
| Metadata Injection                 | `Node.metadata`, `Concept.metadata`                                | Embeds concept link in each node              |

---

Would you like:

* A repo skeleton with these pieces wired?
* Prompt templates for Bloom levels?
* Code to convert results into Supabase insertable JSON?
