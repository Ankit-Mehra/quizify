import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException
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
                "difficulty": "easy",  # Match mocked assignment
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
                "bloom_level": "understand",  # Match mocked assignment
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


# === Error Scenario Tests ===

@pytest.mark.asyncio
async def test_rag_pipeline_quota_exceeded():
    """Test that quota exceeded raises 403 error."""
    user_id = str(uuid4())
    user_token = "fake_token"
    request = EnhancedTextQuizRequest(
        title="Test Quiz",
        content="This is test content about machine learning concepts.",
        num_questions=5,
        question_type="multiple_choice"
    )
    
    with patch("handlers.quiz_handlers.validate_user_quota") as mock_validate_quota:
        # Simulate quota exceeded
        mock_validate_quota.side_effect = HTTPException(
            status_code=403,
            detail={"message": "Quota exceeded", "current_count": 5, "quota_limit": 5}
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_rag_async(request, user_id, user_token)
        
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_rag_pipeline_concept_extraction_failure():
    """Test that empty concept extraction returns descriptive error."""
    user_id = str(uuid4())
    user_token = "fake_token"
    doc_id = str(uuid4())
    
    request = EnhancedTextQuizRequest(
        title="Test Quiz",
        content="This is test content that should fail concept extraction but is long enough to pass validation.",
        num_questions=5,
        question_type="mixed",
        mode="enhanced"  # Force enhanced mode to test concept extraction
    )
    
    with patch("handlers.quiz_handlers.IngestionService") as MockIngestion, \
         patch("handlers.quiz_handlers.ConceptExtractionService") as MockExtraction, \
         patch("handlers.quiz_handlers.validate_user_quota") as mock_validate_quota:
        
        mock_validate_quota.return_value = None
        
        # Setup Ingestion Mock
        ingestion_instance = MockIngestion.return_value
        ingestion_instance.ingest_content = AsyncMock(return_value={"document_id": doc_id, "chunks": []})
        
        # Setup Extraction Mock - returns empty list
        extraction_instance = MockExtraction.return_value
        extraction_instance.extract_concepts = AsyncMock(return_value=[])
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_rag_async(request, user_id, user_token)
        
        # Returns 400 (validation error) with descriptive message
        assert exc_info.value.status_code == 400
        assert "concept" in exc_info.value.detail.lower() or "content" in exc_info.value.detail.lower()


@pytest.mark.asyncio 
async def test_rag_pipeline_all_questions_fail():
    """Test that when all question generations fail, we get descriptive error."""
    user_id = str(uuid4())
    user_token = "fake_token"
    doc_id = str(uuid4())
    concept_id = str(uuid4())
    
    request = EnhancedTextQuizRequest(
        title="Test Quiz",
        content="This is test content for quiz generation testing that is long enough to pass the minimum content validation.",
        num_questions=2,
        question_type="mixed",
        mode="enhanced"
    )
    
    with patch("handlers.quiz_handlers.IngestionService") as MockIngestion, \
         patch("handlers.quiz_handlers.ConceptExtractionService") as MockExtraction, \
         patch("handlers.quiz_handlers.QuizOrchestrationService") as MockOrchestration, \
         patch("handlers.quiz_handlers.validate_user_quota") as mock_validate_quota:
        
        mock_validate_quota.return_value = None
        
        # Setup Ingestion Mock
        ingestion_instance = MockIngestion.return_value
        ingestion_instance.ingest_content = AsyncMock(return_value={"document_id": doc_id, "chunks": []})
        
        # Setup Extraction Mock - returns concepts
        extraction_instance = MockExtraction.return_value
        extraction_instance.extract_concepts = AsyncMock(return_value=[
            {"id": concept_id, "name": "Test Concept", "relevance_score": 0.9}
        ])
        
        # Setup Orchestration Mock - all questions fail
        orchestration_instance = MockOrchestration.return_value
        orchestration_instance.assign_bloom_and_difficulty = MagicMock(return_value=[
            ("remember", "easy"),
            ("understand", "medium")
        ])
        # Simulate all question generations failing
        orchestration_instance.generate_question_for_concept = AsyncMock(
            side_effect=ValueError("Question verification failed")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_rag_async(request, user_id, user_token)
        
        # Should get 400 (validation error) or 500 (generation failure)
        assert exc_info.value.status_code in [400, 500]
        # Should mention that questions failed to generate
        assert "question" in exc_info.value.detail.lower() or "failed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_rag_pipeline_content_too_short():
    """Test that short content returns 400 error."""
    user_id = str(uuid4())
    user_token = "fake_token"
    
    request = EnhancedTextQuizRequest(
        title="Test Quiz",
        content="Too short",  # Below MIN_CONTENT_LENGTH
        num_questions=5,
        question_type="mixed"
    )
    
    with patch("handlers.quiz_handlers.validate_user_quota") as mock_validate_quota:
        mock_validate_quota.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_rag_async(request, user_id, user_token)
        
        assert exc_info.value.status_code == 400
        assert "short" in exc_info.value.detail.lower() or "minimum" in exc_info.value.detail.lower()
