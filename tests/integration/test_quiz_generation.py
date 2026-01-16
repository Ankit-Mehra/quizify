"""
Integration test for complete quiz generation flow.

Tests the full quiz generation journey:
1. Upload file to file storage
2. Generate quiz from uploaded file
3. Verify questions are stored in database
4. Retrieve quiz and validate content
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os
import io
from docx import Document

client = TestClient(app)

TEST_EMAIL = f"test_quiz_flow_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.mark.integration
def create_test_docx(content: str) -> bytes:
    """Create a test DOCX file."""
    doc = Document()
    for paragraph in content.split('\n'):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture(scope="function")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Quiz Flow Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    # If user already exists (from previous test run), try login directly
    if signup_response.status_code != 201:
        # Ensure it's because user exists
        assert signup_response.status_code == 400 or signup_response.status_code == 409
    
    login_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    
    return token

@pytest.mark.integration
class TestQuizGenerationFlow:
    """Integration tests for complete quiz generation workflow."""
    
    def test_complete_quiz_generation_flow_with_file(self, auth_token):
        """
        Test complete flow: Upload file → Generate quiz → Verify storage → Retrieve quiz.
        
        Flow:
        1. Upload file to storage
        2. Generate quiz from file
        3. Verify quiz stored with questions
        4. Retrieve quiz by ID
        5. Verify all data persisted correctly
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Extract cookies from the client (they should have been set during login)
        # TestClient maintains cookies, but we need to ensure they're being sent
        # Note: Cookies are automatically included by TestClient in subsequent requests
        
        # Step 1: Upload file
        file_content = """
        Cloud Computing Fundamentals
        
        Cloud computing delivers computing services over the internet, including servers, storage, databases,
        networking, software, analytics, and intelligence. It offers faster innovation, flexible resources,
        and economies of scale.
        
        Main service models include Infrastructure as a Service (IaaS), Platform as a Service (PaaS),
        and Software as a Service (SaaS). Major cloud providers include AWS, Microsoft Azure, and Google Cloud.
        
        Key benefits include cost savings, scalability, performance, speed, productivity, reliability,
        and security when properly implemented.
        """
        
        docx_bytes = create_test_docx(file_content)
        
        upload_files = {
            "file": ("cloud_computing.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        
        upload_response = client.post("/api/files/upload", headers=headers, files=upload_files)
        
        # File upload might return 200 or 201
        assert upload_response.status_code in [200, 201], \
            f"File upload failed: {upload_response.text}"
        
        upload_data = upload_response.json()
        file_id = upload_data.get("file_id") or upload_data.get("id")
        assert file_id is not None, "File upload should return file_id"
        
        # Step 2: Generate quiz from uploaded file
        quiz_files = {
            "file": ("cloud_computing.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        # For multipart form data with list parameters, provide list directly
        quiz_data = {
            "title": "Cloud Computing Quiz",
            "num_questions": "6",
            "question_type": ["multiple_choice", "true_false"]  # Provide as list, not JSON string
        }
        
        quiz_response = client.post("/api/quiz/generate/upload", headers=headers, files=quiz_files, data=quiz_data)
        
        assert quiz_response.status_code == 201, \
            f"Quiz generation failed: {quiz_response.text}"
        
        quiz_response_data = quiz_response.json()
        quiz_id = quiz_response_data.get("quiz_id") or quiz_response_data.get("id")
        questions = quiz_response_data.get("questions", [])
        
        assert quiz_id is not None, "Quiz generation should return quiz_id"
        assert len(questions) > 0, "Quiz should have questions"
        
        # Step 3: Verify quiz stored - retrieve user's quizzes
        my_quizzes_response = client.get("/api/quiz/my-quizzes", headers=headers)
        
        assert my_quizzes_response.status_code == 200, \
            f"Failed to retrieve user quizzes: {my_quizzes_response.text}"
        
        my_quizzes_data = my_quizzes_response.json()
        assert isinstance(my_quizzes_data, dict), "User quizzes should be a paginated response"
        assert "quizzes" in my_quizzes_data, "Response should contain quizzes key"
        my_quizzes = my_quizzes_data["quizzes"]
        
        # Find our quiz in the list
        our_quiz = next((q for q in my_quizzes if q.get("id") == quiz_id or q.get("quiz_id") == quiz_id), None)
        assert our_quiz is not None, f"Quiz {quiz_id} not found in user's quiz list"
        
        # Step 4: Retrieve specific quiz by ID
        quiz_detail_response = client.get(f"/api/quiz/{quiz_id}", headers=headers)
        
        assert quiz_detail_response.status_code == 200, \
            f"Failed to retrieve quiz details: {quiz_detail_response.text}"
        
        quiz_detail = quiz_detail_response.json()
        
        # Step 5: Verify all data persisted correctly
        assert quiz_detail.get("title") == "Cloud Computing Quiz", "Quiz title should match"
        
        detail_questions = quiz_detail.get("questions", [])
        assert len(detail_questions) > 0, "Quiz details should include questions"
        assert len(detail_questions) == len(questions), "Question count should match"
        
        # Verify question structure
        for question in detail_questions:
            assert "id" in question, "Question should have ID"
            assert "type" in question, "Question should have type"
            assert "question" in question, "Question should have text"
            assert "correct_answer" in question, "Question should have correct answer"
    
    def test_text_based_quiz_generation_flow(self, auth_token):
        """
        Test quiz generation from text (no file upload).
        
        Flow:
        1. Generate quiz from text directly
        2. Retrieve quiz
        3. Verify content
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Step 1: Generate quiz from text
        text_payload = {
            "content": """
            Blockchain Technology
            
            Blockchain is a distributed ledger technology that maintains a secure and decentralized record of transactions.
            Each block contains a cryptographic hash of the previous block, timestamp, and transaction data.
            
            Bitcoin, created by Satoshi Nakamoto, was the first widespread application of blockchain technology.
            Smart contracts, popularized by Ethereum, enable programmable transactions and decentralized applications.
            """,
            "title": "Blockchain Basics Quiz",
            "num_questions": 5,
            "question_type": ["multiple_choice", "true_false"]
        }
        
        quiz_response = client.post("/api/quiz/generate/text", headers=headers, json=text_payload)
        
        assert quiz_response.status_code == 200, \
            f"Text quiz generation failed: {quiz_response.text}"
        
        quiz_data = quiz_response.json()
        quiz_id = quiz_data.get("quiz_id") or quiz_data.get("id")
        
        # Step 2: Retrieve quiz
        detail_response = client.get(f"/api/quiz/{quiz_id}", headers=headers)
        
        assert detail_response.status_code == 200, \
            f"Failed to retrieve quiz: {detail_response.text}"
        
        # Step 3: Verify content
        detail = detail_response.json()
        assert detail.get("title") == "Blockchain Basics Quiz"
        assert len(detail.get("questions", [])) > 0
    
    def test_quiz_persists_after_generation(self, auth_token):
        """
        Test that generated quizzes persist and can be retrieved later.
        
        Verifies:
        - Quiz appears in user's quiz list
        - Quiz can be retrieved multiple times
        - Questions remain consistent
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Generate quiz
        payload = {
            "content": "Database Management Systems store, organize, and manage data efficiently.",
            "title": "DBMS Persistence Test",
            "num_questions": 3,
            "question_type": ["multiple_choice"]
        }
        
        gen_response = client.post("/api/quiz/generate/text", headers=headers, json=payload)
        assert gen_response.status_code == 200
        
        quiz_id = gen_response.json().get("quiz_id") or gen_response.json().get("id")
        expected_question_count = 3  # We requested 3 questions
        
        # Retrieve quiz multiple times
        for _ in range(3):
            detail_response = client.get(f"/api/quiz/{quiz_id}", headers=headers)
            assert detail_response.status_code == 200
            
            questions = detail_response.json().get("questions", [])
            assert len(questions) == expected_question_count, "Question count should remain consistent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
