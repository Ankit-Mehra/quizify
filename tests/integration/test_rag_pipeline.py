import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from schemas.quiz import EnhancedTextQuizRequest
from handlers.quiz_handlers import generate_quiz_rag_async

@pytest.mark.asyncio
async def test_rag_pipeline_flow():
    # Mock data
    user_id = str(uuid4())
    user_token = "fake_token"
    request = EnhancedTextQuizRequest(
        title="Test RAG Quiz",
        content="This is a test content about Photosynthesis. Photosynthesis is the process used by plants.",
        num_questions=2,
        question_type="mixed"
    )
    
    # Generate valid UUIDs for mocks
    doc_id = str(uuid4())
    chunk_id = str(uuid4())
    concept_id_1 = str(uuid4())
    concept_id_2 = str(uuid4())

    # Mock Services
    with patch("handlers.quiz_handlers.IngestionService") as MockIngestion, \
         patch("handlers.quiz_handlers.ConceptExtractionService") as MockExtraction, \
         patch("handlers.quiz_handlers.QuizOrchestrationService") as MockOrchestration, \
         patch("handlers.quiz_handlers.save_quiz_to_database") as mock_save, \
         patch("handlers.quiz_handlers.validate_user_quota") as mock_validate_quota:
        
        # Setup Quota Validation Mock (user has quota)
        mock_validate_quota.return_value = None  # No exception = quota valid
        
        # Setup Ingestion Mock
        ingestion_instance = MockIngestion.return_value
        ingestion_instance.ingest_content = AsyncMock(return_value={"document_id": doc_id})
        
        # Setup Extraction Mock
        extraction_instance = MockExtraction.return_value
        extraction_instance.extract_concepts = AsyncMock(return_value=[
            {"id": concept_id_1, "name": "Photosynthesis", "relevance_score": 0.9},
            {"id": concept_id_2, "name": "Plants", "relevance_score": 0.8}
        ])
        
        # Setup Orchestration Mock
        orchestration_instance = MockOrchestration.return_value
        # Mock assign_bloom_and_difficulty to return pairs for 2 questions
        orchestration_instance.assign_bloom_and_difficulty = MagicMock(return_value=[
            ("remember", "easy"),
            ("understand", "medium")
        ])
        orchestration_instance.generate_question_for_concept = AsyncMock(side_effect=[
            {
                "type": "multiple_choice",
                "question": "What is photosynthesis?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
                "explanation": "Exp",
                "source": "RAG",
                "bloom_level": "remember",
                "difficulty": "medium",
                "concept_id": concept_id_1,
                "chunk_id": chunk_id,
                "confidence_score": 0.9
            },
            {
                "type": "true_false",
                "question": "Plants use photosynthesis.",
                "correct_answer": True,
                "explanation": "Exp",
                "source": "RAG",
                "bloom_level": "remember",
                "difficulty": "medium",
                "concept_id": concept_id_2,
                "chunk_id": chunk_id,
                "confidence_score": 0.95
            }
        ])
        
        # Setup Save Mock
        mock_save.return_value = ("quiz_123", [])
        
        # Run Handler
        response = await generate_quiz_rag_async(request, user_id, user_token)
        
        # Assertions
        assert response.quiz_id == "quiz_123"
        assert len(response.questions) == 2
        assert response.questions[0].question == "What is photosynthesis?"
        
        # Verify calls
        ingestion_instance.ingest_content.assert_called_once()
        extraction_instance.extract_concepts.assert_called_once()
        assert orchestration_instance.generate_question_for_concept.call_count == 2
        mock_save.assert_called_once()
