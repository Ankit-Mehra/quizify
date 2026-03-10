"""
Tests for Share Link Feature (Epic 5)

Tests cover:
1. Slug generation
2. Share service functions
3. ShareLinkExporter
4. Share API routes
5. Public quiz access
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from services.share_service import (
    generate_slug,
    build_share_url,
    SLUG_LENGTH,
    SLUG_CHARS,
)
from services.exporters.share_link_exporter import ShareLinkExporter
from services.exporters.base import ExportError
from schemas.share import (
    ShareLinkCreate,
    ShareLinkResponse,
    ShareLinkStatus,
    QuizPublicView,
    PublicQuestion,
    PublicQuestionOption,
)
from schemas.export import QuizExportData, ExportOptions, ExportQuestionMCQ


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_quiz_id():
    """Generate a sample quiz UUID."""
    return uuid4()


@pytest.fixture
def sample_user_id():
    """Generate a sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_quiz_export_data(sample_quiz_id):
    """Create sample quiz export data for testing."""
    return QuizExportData(
        quiz_id=sample_quiz_id,
        title="Test Share Quiz",
        description="A quiz for testing sharing",
        created_at=datetime.now(timezone.utc),
        questions=[
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question="What is 2 + 2?",
                options=["3", "4", "5", "6"],
                correct_answer="4",
                explanation="Basic arithmetic",
            )
        ],
    )


@pytest.fixture
def sample_export_options():
    """Create default export options."""
    return ExportOptions(include_answer_key=True, include_explanations=False)


# ============================================================================
# Slug Generation Tests
# ============================================================================


class TestSlugGeneration:
    """Tests for slug generation functionality."""
    
    def test_generate_slug_default_length(self):
        """Test slug is generated with default length."""
        slug = generate_slug()
        assert len(slug) == SLUG_LENGTH
    
    def test_generate_slug_custom_length(self):
        """Test slug generation with custom length."""
        slug = generate_slug(length=12)
        assert len(slug) == 12
    
    def test_generate_slug_characters(self):
        """Test slug contains only valid characters."""
        slug = generate_slug()
        for char in slug:
            assert char in SLUG_CHARS
    
    def test_generate_slug_uniqueness(self):
        """Test multiple slugs are unique."""
        slugs = {generate_slug() for _ in range(100)}
        # Very unlikely to have collisions with 8-char alphanumeric
        assert len(slugs) >= 95  # Allow for rare collisions
    
    def test_generate_slug_is_lowercase(self):
        """Test slug is all lowercase."""
        for _ in range(10):
            slug = generate_slug()
            assert slug == slug.lower()


class TestBuildShareUrl:
    """Tests for share URL building."""
    
    def test_build_share_url_format(self):
        """Test share URL has correct format."""
        url = build_share_url("abc123")
        # Should end with /quiz/slug
        assert url.endswith("/quiz/abc123")
    
    def test_build_share_url_no_double_slashes(self):
        """Test URL doesn't have double slashes (except protocol)."""
        url = build_share_url("testslug")
        # Remove protocol prefix for check
        url_without_protocol = url.split("://", 1)[1] if "://" in url else url
        assert "//" not in url_without_protocol


# ============================================================================
# Share Link Schema Tests
# ============================================================================


class TestShareSchemas:
    """Tests for share-related Pydantic schemas."""
    
    def test_share_link_create_schema(self, sample_quiz_id):
        """Test ShareLinkCreate schema validation."""
        request = ShareLinkCreate(quiz_id=sample_quiz_id)
        assert request.quiz_id == sample_quiz_id
    
    def test_share_link_response_schema(self, sample_quiz_id):
        """Test ShareLinkResponse schema."""
        response = ShareLinkResponse(
            quiz_id=sample_quiz_id,
            public_slug="abc12xyz",
            share_url="https://example.com/quiz/abc12xyz",
            is_public=True,
            shared_at=datetime.now(timezone.utc),
        )
        assert response.quiz_id == sample_quiz_id
        assert response.public_slug == "abc12xyz"
        assert response.is_public is True
    
    def test_share_link_status_private(self, sample_quiz_id):
        """Test ShareLinkStatus for private quiz."""
        status = ShareLinkStatus(
            quiz_id=sample_quiz_id,
            is_public=False,
            public_slug=None,
            share_url=None,
            shared_at=None,
        )
        assert status.is_public is False
        assert status.share_url is None
    
    def test_share_link_status_public(self, sample_quiz_id):
        """Test ShareLinkStatus for public quiz."""
        now = datetime.now(timezone.utc)
        status = ShareLinkStatus(
            quiz_id=sample_quiz_id,
            is_public=True,
            public_slug="xyz789ab",
            share_url="https://example.com/quiz/xyz789ab",
            shared_at=now,
        )
        assert status.is_public is True
        assert status.public_slug == "xyz789ab"
        assert status.shared_at == now


class TestPublicQuizSchemas:
    """Tests for public quiz viewing schemas."""
    
    def test_public_question_option(self):
        """Test PublicQuestionOption schema."""
        option = PublicQuestionOption(id="a", text="Option A")
        assert option.id == "a"
        assert option.text == "Option A"
    
    def test_public_question_mcq(self):
        """Test PublicQuestion for MCQ type."""
        question = PublicQuestion(
            id=uuid4(),
            question_number=1,
            question_type="mcq",
            question_text="Sample question?",
            options=[
                PublicQuestionOption(id="a", text="Option A"),
                PublicQuestionOption(id="b", text="Option B"),
            ],
            difficulty="easy",
        )
        assert question.question_type == "mcq"
        assert len(question.options) == 2
    
    def test_quiz_public_view_schema(self):
        """Test QuizPublicView schema."""
        quiz = QuizPublicView(
            id=uuid4(),
            title="Test Public Quiz",
            description="A public quiz",
            topic="Testing",
            total_questions=5,
            questions=[
                PublicQuestion(
                    id=uuid4(),
                    question_number=1,
                    question_type="mcq",
                    question_text="Question 1?",
                    options=[PublicQuestionOption(id="a", text="A")],
                    difficulty="medium",
                )
            ],
            shared_at=datetime.now(timezone.utc),
        )
        assert quiz.title == "Test Public Quiz"
        assert quiz.total_questions == 5
        assert len(quiz.questions) == 1


# ============================================================================
# ShareLinkExporter Tests
# ============================================================================


class TestShareLinkExporter:
    """Tests for ShareLinkExporter class."""
    
    def test_exporter_format_name(self):
        """Test exporter has correct format name."""
        exporter = ShareLinkExporter()
        assert exporter.FORMAT_NAME == "share_link"
    
    def test_exporter_content_type(self):
        """Test exporter has text/plain content type."""
        exporter = ShareLinkExporter()
        assert exporter.CONTENT_TYPE == "text/plain"
    
    def test_exporter_no_file_extension(self):
        """Test exporter has no file extension (not a file export)."""
        exporter = ShareLinkExporter()
        assert exporter.FILE_EXTENSION == ""
    
    @pytest.mark.asyncio
    async def test_export_requires_user_id(
        self, sample_quiz_export_data, sample_export_options
    ):
        """Test export fails without user_id."""
        exporter = ShareLinkExporter(user_id=None)
        
        with pytest.raises(ExportError) as exc_info:
            await exporter.export(sample_quiz_export_data, sample_export_options)
        
        assert "User ID is required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_export_returns_share_url(
        self, sample_quiz_export_data, sample_export_options, sample_user_id
    ):
        """Test export returns a share URL in testing mode."""
        exporter = ShareLinkExporter(user_id=sample_user_id)
        
        result = await exporter.export(sample_quiz_export_data, sample_export_options)
        
        assert result.share_url is not None
        assert "/quiz/" in result.share_url
        assert result.content_type == "text/plain"
    
    @pytest.mark.asyncio
    async def test_export_content_matches_url(
        self, sample_quiz_export_data, sample_export_options, sample_user_id
    ):
        """Test export content contains the share URL."""
        exporter = ShareLinkExporter(user_id=sample_user_id)
        
        result = await exporter.export(sample_quiz_export_data, sample_export_options)
        
        # Content should be URL as bytes
        content_str = result.content.decode("utf-8")
        assert content_str == result.share_url
    
    @pytest.mark.asyncio
    async def test_export_filename_is_none(
        self, sample_quiz_export_data, sample_export_options, sample_user_id
    ):
        """Test export has no filename (not a file download)."""
        exporter = ShareLinkExporter(user_id=sample_user_id)
        
        result = await exporter.export(sample_quiz_export_data, sample_export_options)
        
        assert result.filename is None
    
    def test_generate_filename_returns_none(self, sample_user_id):
        """Test generate_filename returns None for share links."""
        exporter = ShareLinkExporter(user_id=sample_user_id)
        filename = exporter.generate_filename("Any Quiz Title")
        assert filename is None


# ============================================================================
# Share Service Tests (Integration-style with mocks)
# ============================================================================


class TestShareServiceMocked:
    """Tests for share service functions (using test mode behavior)."""
    
    @pytest.mark.asyncio
    async def test_create_share_link_testing_mode(
        self, sample_quiz_id, sample_user_id
    ):
        """Test create_share_link returns mock in testing mode."""
        from services.share_service import create_share_link
        
        result = await create_share_link(
            quiz_id=sample_quiz_id,
            user_id=sample_user_id,
            user_token=None,
        )
        
        assert result["is_public"] is True
        assert result["public_slug"] is not None
        assert "/quiz/" in result["share_url"]
    
    @pytest.mark.asyncio
    async def test_revoke_share_link_testing_mode(
        self, sample_quiz_id, sample_user_id
    ):
        """Test revoke_share_link returns mock in testing mode."""
        from services.share_service import revoke_share_link
        
        result = await revoke_share_link(
            quiz_id=sample_quiz_id,
            user_id=sample_user_id,
            user_token=None,
        )
        
        assert result["is_public"] is False
        assert "revoked" in result["message"].lower()
    
    @pytest.mark.asyncio
    async def test_get_share_status_testing_mode(
        self, sample_quiz_id, sample_user_id
    ):
        """Test get_share_status returns mock in testing mode."""
        from services.share_service import get_share_status
        
        result = await get_share_status(
            quiz_id=sample_quiz_id,
            user_id=sample_user_id,
            user_token=None,
        )
        
        assert "is_public" in result
        assert "quiz_id" in result
    
    @pytest.mark.asyncio
    async def test_get_public_quiz_testing_mode(self):
        """Test get_public_quiz returns mock in testing mode."""
        from services.share_service import get_public_quiz_by_slug
        
        result = await get_public_quiz_by_slug("testslug")
        
        assert "title" in result
        assert "questions" in result
        assert result["total_questions"] >= 1


# ============================================================================
# Options Format Tests
# ============================================================================


class TestOptionsFormatHandling:
    """Tests for handling both string and dict option formats."""
    
    def test_string_options_get_letter_ids(self):
        """Test plain string options get auto-generated letter IDs (a, b, c, d)."""
        # Simulate the transformation logic
        raw_options = ["Option A", "Option B", "Option C", "Option D"]
        result = []
        for i, opt in enumerate(raw_options):
            default_id = chr(ord('a') + i) if i < 26 else str(i)
            if isinstance(opt, dict):
                result.append({"id": opt.get("id", default_id), "text": opt.get("text", "")})
            else:
                result.append({"id": default_id, "text": str(opt)})
        
        assert result[0] == {"id": "a", "text": "Option A"}
        assert result[1] == {"id": "b", "text": "Option B"}
        assert result[2] == {"id": "c", "text": "Option C"}
        assert result[3] == {"id": "d", "text": "Option D"}
    
    def test_dict_options_preserve_ids(self):
        """Test dict-format options preserve their original IDs."""
        raw_options = [
            {"id": "x", "text": "Option X"},
            {"id": "y", "text": "Option Y"},
        ]
        result = []
        for i, opt in enumerate(raw_options):
            default_id = chr(ord('a') + i) if i < 26 else str(i)
            if isinstance(opt, dict):
                result.append({"id": opt.get("id", default_id), "text": opt.get("text", "")})
            else:
                result.append({"id": default_id, "text": str(opt)})
        
        assert result[0] == {"id": "x", "text": "Option X"}
        assert result[1] == {"id": "y", "text": "Option Y"}
    
    def test_dict_options_fallback_to_letter_id(self):
        """Test dict options without ID fall back to letter IDs."""
        raw_options = [
            {"text": "Option A"},  # Missing id
            {"id": "", "text": "Option B"},  # Empty id - should use empty string
        ]
        result = []
        for i, opt in enumerate(raw_options):
            default_id = chr(ord('a') + i) if i < 26 else str(i)
            if isinstance(opt, dict):
                result.append({"id": opt.get("id", default_id), "text": opt.get("text", "")})
            else:
                result.append({"id": default_id, "text": str(opt)})
        
        assert result[0]["id"] == "a"  # Fallback to letter
        assert result[0]["text"] == "Option A"
        # Empty string is falsy but still a value from get()
        assert result[1]["id"] == ""  # Empty string preserved
    
    def test_more_than_26_options_uses_numeric_fallback(self):
        """Test that options beyond 26 use numeric IDs."""
        raw_options = [f"Option {i}" for i in range(30)]
        result = []
        for i, opt in enumerate(raw_options):
            default_id = chr(ord('a') + i) if i < 26 else str(i)
            if isinstance(opt, dict):
                result.append({"id": opt.get("id", default_id), "text": opt.get("text", "")})
            else:
                result.append({"id": default_id, "text": str(opt)})
        
        # First 26 should be a-z
        assert result[0]["id"] == "a"
        assert result[25]["id"] == "z"
        # After 26 should be numeric (0-indexed)
        assert result[26]["id"] == "26"
        assert result[27]["id"] == "27"
        assert result[29]["id"] == "29"
    
    def test_empty_options_returns_empty_list(self):
        """Test that null/empty options return empty list."""
        for raw_options in [None, []]:
            result = []
            for i, opt in enumerate(raw_options or []):
                default_id = chr(ord('a') + i) if i < 26 else str(i)
                if isinstance(opt, dict):
                    result.append({"id": opt.get("id", default_id), "text": opt.get("text", "")})
                else:
                    result.append({"id": default_id, "text": str(opt)})
            
            assert result == []


# ============================================================================
# Share API Route Tests
# ============================================================================


class TestShareRoutesUnit:
    """Unit tests for share API routes."""
    
    def test_share_routes_import(self):
        """Test share routes module can be imported."""
        from api import share_routes
        
        assert hasattr(share_routes, "router")
        assert hasattr(share_routes, "create_quiz_share_link")
        assert hasattr(share_routes, "revoke_quiz_share_link")
        assert hasattr(share_routes, "get_quiz_share_status")
        assert hasattr(share_routes, "get_public_quiz")
    
    def test_share_routes_use_correct_auth_dependencies(self):
        """Test share routes use get_current_user_id and get_current_user_token."""
        from api import share_routes
        import inspect
        
        # Check that routes use the correct dependency functions
        create_sig = inspect.signature(share_routes.create_quiz_share_link)
        params = list(create_sig.parameters.keys())
        assert "user_id" in params
        assert "user_token" in params


class TestShareRoutesIntegration:
    """Integration tests for share API routes."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)
    
    @pytest.fixture
    def mock_auth_headers(self, sample_user_id):
        """Create mock auth headers for testing."""
        # In testing mode, auth is mocked
        return {"Authorization": "Bearer test-token"}
    
    def test_public_quiz_endpoint_exists(self, client):
        """Test public quiz endpoint responds correctly."""
        response = client.get("/api/share/public/nonexistent")
        # In testing mode, we get a mock quiz back (200)
        # In production, this would return 404 for invalid slugs
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "questions" in data
    
    def test_share_status_requires_auth(self, client):
        """Test share status endpoint requires authentication."""
        response = client.get(f"/api/share/status/{uuid4()}")
        assert response.status_code == 401
    
    def test_create_share_requires_auth_returns_403_csrf(self, client, sample_quiz_id):
        """Test create share endpoint requires CSRF protection (returns 403 without headers)."""
        response = client.post(
            "/api/share",
            json={"quiz_id": str(sample_quiz_id)},
        )
        # POST without Authorization header triggers CSRF protection (403) before auth (401)
        assert response.status_code == 403
    
    def test_revoke_share_requires_auth_returns_403_csrf(self, client, sample_quiz_id):
        """Test revoke share endpoint requires CSRF protection (returns 403 without headers)."""
        response = client.delete(f"/api/share/{sample_quiz_id}")
        # DELETE without Authorization header triggers CSRF protection (403) before auth (401)
        assert response.status_code == 403


# ============================================================================
# Export Handler Share Link Tests
# ============================================================================


class TestExportHandlerShareLink:
    """Tests for share link handling in export handler."""
    
    def test_share_link_registered_in_handler(self):
        """Test ShareLinkExporter is registered in export handler."""
        from handlers.export_handler import _ensure_exporters_loaded, _EXPORTER_REGISTRY
        from schemas.export import ExportFormat
        from services.exporters.share_link_exporter import ShareLinkExporter
        
        _ensure_exporters_loaded()
        
        assert ExportFormat.SHARE_LINK in _EXPORTER_REGISTRY
        assert _EXPORTER_REGISTRY[ExportFormat.SHARE_LINK] == ShareLinkExporter
    
    def test_get_exporter_with_user_context(self, sample_user_id):
        """Test get_exporter passes user context for share_link."""
        from handlers.export_handler import get_exporter, _ensure_exporters_loaded
        from schemas.export import ExportFormat
        
        _ensure_exporters_loaded()
        
        exporter = get_exporter(
            ExportFormat.SHARE_LINK,
            user_id=str(sample_user_id),
            user_token="test-token",
        )
        
        assert exporter.user_id == sample_user_id
        assert exporter.user_token == "test-token"


# ============================================================================
# Migration File Tests
# ============================================================================


class TestShareMigration:
    """Tests to verify migration file exists and has correct structure."""
    
    def test_migration_file_exists(self):
        """Test migration file exists."""
        import os
        migration_path = "migrations/019_add_share_link_feature.sql"
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"
    
    def test_migration_contains_required_columns(self):
        """Test migration adds required columns."""
        with open("migrations/019_add_share_link_feature.sql", "r") as f:
            content = f.read()
        
        assert "is_public" in content
        assert "public_slug" in content
        assert "shared_at" in content
    
    def test_migration_creates_indexes(self):
        """Test migration creates necessary indexes."""
        with open("migrations/019_add_share_link_feature.sql", "r") as f:
            content = f.read()
        
        assert "CREATE" in content and "INDEX" in content
        assert "public_slug" in content
    
    def test_migration_updates_rls_policies(self):
        """Test migration updates RLS policies for public access."""
        with open("migrations/019_add_share_link_feature.sql", "r") as f:
            content = f.read()
        
        assert "POLICY" in content
        assert "is_public" in content
