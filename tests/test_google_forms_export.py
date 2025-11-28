"""
Tests for Google Forms Export Feature (Epic QUIZ-002).

This module tests:
- GoogleFormsExporter class
- Google OAuth service
- Tier validation for Google Forms export
- API endpoints for Google OAuth
"""

import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timezone

# Import test subjects
from schemas.export import ExportFormat
from services.exporters.tier_validator import (
    validate_export_tier_access,
    TierInsufficientError,
    is_format_available_for_tier,
    get_available_formats_for_tier,
    PRO_ONLY_FORMATS,
    PAID_TIER_FORMATS
)


class TestGoogleFormsExportFormat:
    """Test Google Forms is properly added to export formats."""
    
    def test_google_forms_in_export_format_enum(self):
        """GOOGLE_FORMS should be a valid ExportFormat."""
        assert hasattr(ExportFormat, "GOOGLE_FORMS")
        assert ExportFormat.GOOGLE_FORMS.value == "google_forms"
    
    def test_google_forms_in_pro_only_formats(self):
        """GOOGLE_FORMS should be in PRO_ONLY_FORMATS (Pro tier only)."""
        assert ExportFormat.GOOGLE_FORMS in PRO_ONLY_FORMATS
        assert ExportFormat.GOOGLE_FORMS not in PAID_TIER_FORMATS
    
    def test_pro_only_formats_contains_all_pro_features(self):
        """PRO_ONLY_FORMATS should contain Google Forms and LMS formats."""
        assert ExportFormat.QTI in PRO_ONLY_FORMATS
        assert ExportFormat.MOODLE_XML in PRO_ONLY_FORMATS
        assert ExportFormat.GOOGLE_FORMS in PRO_ONLY_FORMATS
        assert len(PRO_ONLY_FORMATS) == 3


class TestTierValidationForGoogleForms:
    """Test tier-based access control for Google Forms export."""
    
    def test_free_tier_cannot_access_google_forms(self):
        """Free tier users should not access Google Forms export."""
        with pytest.raises(TierInsufficientError) as exc_info:
            validate_export_tier_access("free", ExportFormat.GOOGLE_FORMS)
        
        assert exc_info.value.status_code == 403
        assert "tier_insufficient" in str(exc_info.value.detail)
    
    def test_premium_tier_cannot_access_google_forms(self):
        """Premium tier users should NOT access Google Forms export (Pro only)."""
        with pytest.raises(TierInsufficientError) as exc_info:
            validate_export_tier_access("premium", ExportFormat.GOOGLE_FORMS)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["required_tier"] == "pro"
    
    def test_basic_tier_cannot_access_google_forms(self):
        """Legacy 'basic' tier (maps to premium) should NOT access Google Forms."""
        with pytest.raises(TierInsufficientError):
            validate_export_tier_access("basic", ExportFormat.GOOGLE_FORMS)
    
    def test_pro_tier_can_access_google_forms(self):
        """Pro tier users should access Google Forms export."""
        # Should not raise
        validate_export_tier_access("pro", ExportFormat.GOOGLE_FORMS)
    
    def test_is_format_available_for_tier(self):
        """Test is_format_available_for_tier helper."""
        assert is_format_available_for_tier("free", ExportFormat.GOOGLE_FORMS) is False
        assert is_format_available_for_tier("premium", ExportFormat.GOOGLE_FORMS) is False
        assert is_format_available_for_tier("basic", ExportFormat.GOOGLE_FORMS) is False  # Legacy mapping to premium
        assert is_format_available_for_tier("pro", ExportFormat.GOOGLE_FORMS) is True
    
    def test_get_available_formats_for_tier(self):
        """Test get_available_formats_for_tier includes/excludes Google Forms."""
        free_formats = get_available_formats_for_tier("free")
        premium_formats = get_available_formats_for_tier("premium")
        pro_formats = get_available_formats_for_tier("pro")
        
        assert ExportFormat.GOOGLE_FORMS not in free_formats
        assert ExportFormat.GOOGLE_FORMS not in premium_formats  # Pro only
        assert ExportFormat.GOOGLE_FORMS in pro_formats


class TestGoogleFormsExporterImports:
    """Test that GoogleFormsExporter can be imported."""
    
    def test_exporter_import(self):
        """GoogleFormsExporter should be importable."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        assert GoogleFormsExporter is not None
    
    def test_exporter_from_package(self):
        """GoogleFormsExporter should be exported from package."""
        from services.exporters import GoogleFormsExporter
        assert GoogleFormsExporter is not None


class TestGoogleFormsExporterClass:
    """Test GoogleFormsExporter class structure and methods."""
    
    def test_exporter_has_correct_format_name(self):
        """Exporter FORMAT_NAME should be 'google_forms'."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        assert exporter.FORMAT_NAME == "google_forms"
    
    def test_exporter_content_type_is_json(self):
        """Exporter CONTENT_TYPE should be application/json."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        assert exporter.CONTENT_TYPE == "application/json"
    
    def test_exporter_has_no_file_extension(self):
        """Exporter FILE_EXTENSION should be empty (returns URL, not file)."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        assert exporter.FILE_EXTENSION == ""
    
    def test_exporter_inherits_from_base(self):
        """GoogleFormsExporter should inherit from BaseExporter."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        from services.exporters.base import BaseExporter
        
        assert issubclass(GoogleFormsExporter, BaseExporter)
    
    @pytest.mark.asyncio
    async def test_export_requires_credentials(self):
        """export() should raise error if user_id not provided."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        from services.exporters.base import ExportError
        from schemas.export import QuizExportData, ExportOptions, ExportQuestionMCQ
        
        # Create minimal quiz data
        quiz_data = QuizExportData(
            quiz_id=uuid4(),
            title="Test Quiz",
            created_at=datetime.now(timezone.utc),
            questions=[
                ExportQuestionMCQ(
                    id=uuid4(),
                    type="multiple_choice",
                    question="Test question?",
                    options=["A", "B", "C", "D"],
                    correct_answer="A"
                )
            ]
        )
        options = ExportOptions(include_answer_key=True)
        
        # Exporter without user_id should raise error
        exporter_no_user = GoogleFormsExporter(user_id=None)
        with pytest.raises(ExportError) as exc_info:
            await exporter_no_user.export(quiz_data, options)
        
        assert "user id required" in str(exc_info.value).lower()


class TestGoogleAuthServiceImports:
    """Test Google Auth service imports."""
    
    def test_service_import(self):
        """google_auth_service should be importable."""
        from services import google_auth_service
        assert google_auth_service is not None
    
    def test_key_functions_exist(self):
        """Key functions should exist in google_auth_service."""
        from services.google_auth_service import (
            is_google_auth_configured,
            generate_auth_url,
            exchange_code_for_tokens,
            build_credentials_from_refresh_token,
            store_google_tokens,
            get_google_credentials,
            disconnect_google,
            is_user_connected,
            GoogleAuthError
        )
        
        assert callable(is_google_auth_configured)
        assert callable(generate_auth_url)
        assert callable(exchange_code_for_tokens)
        assert callable(build_credentials_from_refresh_token)
        assert callable(store_google_tokens)
        assert callable(get_google_credentials)
        assert callable(disconnect_google)
        assert callable(is_user_connected)
        assert issubclass(GoogleAuthError, Exception)


class TestGoogleAuthServiceFunctions:
    """Test Google Auth service functions."""
    
    def test_is_google_auth_configured_without_env(self):
        """is_google_auth_configured returns False without env vars."""
        from services.google_auth_service import is_google_auth_configured
        
        # Mock the module-level constants at the point where they're read
        # This is more reliable than reloading modules and doesn't affect other tests
        with patch(
            'services.google_auth_service.GOOGLE_CLIENT_ID', ''
        ), patch(
            'services.google_auth_service.GOOGLE_CLIENT_SECRET', ''
        ):
            # With empty values, should return False
            assert is_google_auth_configured() is False
    
    def test_generate_auth_url_requires_config(self):
        """generate_auth_url should raise error without config."""
        from services.google_auth_service import (
            generate_auth_url, 
            GoogleAuthError,
            is_google_auth_configured
        )
        
        if not is_google_auth_configured():
            with pytest.raises(GoogleAuthError) as exc_info:
                generate_auth_url()
            
            assert "not configured" in str(exc_info.value).lower()


class TestTokenEncryption:
    """Test token encryption/decryption functions."""
    
    def test_encrypt_decrypt_roundtrip_with_key(self):
        """Token should survive encrypt/decrypt roundtrip when key is configured."""
        from cryptography.fernet import Fernet
        
        # Generate a test key
        test_key = Fernet.generate_key().decode()
        
        with patch.object(
            __import__('config', fromlist=['config']).config,
            'GOOGLE_TOKEN_ENCRYPTION_KEY',
            test_key
        ):
            # Reload to pick up the key
            import services.google_auth_service as gas
            # Reset the cached fernet
            gas._fernet = None
            gas._encryption_warned = False
            
            original_token = "test_refresh_token_12345"
            
            # Encrypt
            encrypted = gas._encrypt_token(original_token)
            assert encrypted != original_token  # Should be different
            
            # Decrypt
            decrypted = gas._decrypt_token(encrypted)
            assert decrypted == original_token  # Should match original
    
    def test_encrypt_returns_plaintext_without_key(self):
        """Without encryption key, _encrypt_token returns plaintext."""
        with patch.object(
            __import__('config', fromlist=['config']).config,
            'GOOGLE_TOKEN_ENCRYPTION_KEY',
            None
        ):
            import services.google_auth_service as gas
            # Reset the cached fernet
            gas._fernet = None
            gas._encryption_warned = False
            
            original_token = "test_refresh_token_no_key"
            encrypted = gas._encrypt_token(original_token)
            
            # Should be the same since no key configured
            assert encrypted == original_token
    
    def test_decrypt_returns_input_without_key(self):
        """Without encryption key, _decrypt_token returns input unchanged."""
        with patch.object(
            __import__('config', fromlist=['config']).config,
            'GOOGLE_TOKEN_ENCRYPTION_KEY',
            None
        ):
            import services.google_auth_service as gas
            # Reset the cached fernet
            gas._fernet = None
            gas._encryption_warned = False
            
            token = "some_token_value"
            decrypted = gas._decrypt_token(token)
            
            assert decrypted == token
    
    def test_decrypt_raises_on_corrupted_token_with_key(self):
        """With encryption key, _decrypt_token raises on invalid/corrupted token."""
        from cryptography.fernet import Fernet
        
        # Generate a test key
        test_key = Fernet.generate_key().decode()
        
        with patch.object(
            __import__('config', fromlist=['config']).config,
            'GOOGLE_TOKEN_ENCRYPTION_KEY',
            test_key
        ):
            import services.google_auth_service as gas
            from services.google_auth_service import TokenDecryptionError
            # Reset the cached fernet
            gas._fernet = None
            gas._encryption_warned = False
            
            # Try to decrypt a corrupted/invalid token
            corrupted_token = "not_a_valid_encrypted_token"
            
            with pytest.raises(TokenDecryptionError) as exc_info:
                gas._decrypt_token(corrupted_token)
            
            assert "corrupted" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()
    
    def test_encryption_functions_exist(self):
        """Encryption functions should be importable."""
        from services.google_auth_service import _encrypt_token, _decrypt_token
        
        assert callable(_encrypt_token)
        assert callable(_decrypt_token)


class TestGoogleAuthHandlers:
    """Test Google OAuth handler functions exist."""
    
    def test_handlers_exist(self):
        """Google OAuth handlers should exist."""
        from handlers.auth_handlers import (
            google_connect,
            google_callback,
            google_disconnect,
            google_status
        )
        
        assert callable(google_connect)
        assert callable(google_callback)
        assert callable(google_disconnect)
        assert callable(google_status)


class TestGoogleAuthRoutes:
    """Test Google OAuth routes are registered."""
    
    def test_google_routes_in_auth_router(self):
        """Google OAuth routes should be registered in auth router."""
        from api.auth_routes import router
        
        route_paths = [route.path for route in router.routes]
        
        # Routes include the /auth prefix from the router
        assert "/auth/google/connect" in route_paths
        assert "/auth/google/callback" in route_paths
        assert "/auth/google/disconnect" in route_paths
        assert "/auth/google/status" in route_paths


class TestMigrationFile:
    """Test database migration for Google OAuth tokens."""
    
    def test_migration_file_exists(self):
        """Migration file for Google OAuth should exist."""
        import os
        
        migration_path = "migrations/019_add_google_oauth_tokens.sql"
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"
    
    def test_migration_adds_google_columns(self):
        """Migration should add Google OAuth columns to profiles."""
        with open("migrations/019_add_google_oauth_tokens.sql", "r") as f:
            content = f.read()
        
        assert "google_refresh_token" in content
        assert "google_connected_at" in content
        assert "profiles" in content
    
    def test_migration_creates_index(self):
        """Migration should create index for connected users."""
        with open("migrations/019_add_google_oauth_tokens.sql", "r") as f:
            content = f.read()
        
        assert "idx_profiles_google_connected" in content
        assert "CREATE INDEX" in content
    
    def test_migration_updates_view(self):
        """Migration should update user_tier_info view."""
        with open("migrations/019_add_google_oauth_tokens.sql", "r") as f:
            content = f.read()
        
        assert "user_tier_info" in content
        assert "google_connected" in content


class TestExportSchemas:
    """Test export schema updates for Google Forms."""
    
    def test_google_forms_response_schema_exists(self):
        """GoogleFormsExportResponse schema should exist."""
        from schemas.export import GoogleFormsExportResponse
        
        assert GoogleFormsExportResponse is not None
    
    def test_google_forms_response_has_required_fields(self):
        """GoogleFormsExportResponse should have form_url, edit_url, form_id."""
        from schemas.export import GoogleFormsExportResponse
        
        fields = GoogleFormsExportResponse.model_fields
        
        assert "form_url" in fields
        assert "edit_url" in fields
        assert "form_id" in fields
    
    def test_google_auth_required_response_exists(self):
        """GoogleAuthRequiredResponse schema should exist."""
        from schemas.export import GoogleAuthRequiredResponse
        
        assert GoogleAuthRequiredResponse is not None
    
    def test_google_auth_required_response_fields(self):
        """GoogleAuthRequiredResponse should have error, message, auth_url."""
        from schemas.export import GoogleAuthRequiredResponse
        
        fields = GoogleAuthRequiredResponse.model_fields
        
        assert "error" in fields
        assert "message" in fields
        assert "auth_url" in fields
        assert "current_tier" in fields


class TestQuestionTypeMapping:
    """Test question type mapping to Google Forms API."""
    
    def test_mcq_item_structure(self):
        """MCQ should map to RADIO choiceQuestion."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        from schemas.export import ExportQuestionMCQ, ExportOptions
        
        exporter = GoogleFormsExporter()
        
        question = ExportQuestionMCQ(
            id=uuid4(),
            type="multiple_choice",
            question="What is 2+2?",
            options=["3", "4", "5", "6"],
            correct_answer="4"
        )
        options = ExportOptions(include_answer_key=True)
        
        item = exporter._build_mcq_item(question, 0, options)
        
        # Check structure
        assert "item" in item
        assert "location" in item
        assert item["location"]["index"] == 0
        
        # Check question item
        question_item = item["item"]["questionItem"]["question"]
        assert "choiceQuestion" in question_item
        assert question_item["choiceQuestion"]["type"] == "RADIO"
        assert len(question_item["choiceQuestion"]["options"]) == 4
        
        # Check grading
        assert "grading" in question_item
        assert question_item["grading"]["pointValue"] == 1
        assert question_item["grading"]["correctAnswers"]["answers"][0]["value"] == "4"
    
    def test_true_false_item_structure(self):
        """True/False should map to RADIO with True/False options."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        from schemas.export import ExportQuestionTrueFalse, ExportOptions
        
        exporter = GoogleFormsExporter()
        
        question = ExportQuestionTrueFalse(
            id=uuid4(),
            type="true_false",
            question="The sky is blue.",
            correct_answer=True
        )
        options = ExportOptions(include_answer_key=True)
        
        item = exporter._build_true_false_item(question, 0, options)
        
        question_item = item["item"]["questionItem"]["question"]
        assert question_item["choiceQuestion"]["type"] == "RADIO"
        
        # Check options are True/False
        option_values = [
            opt["value"] for opt in question_item["choiceQuestion"]["options"]
        ]
        assert "True" in option_values
        assert "False" in option_values
        
        # Check correct answer is True
        assert question_item["grading"]["correctAnswers"]["answers"][0]["value"] == "True"
    
    def test_fill_blank_item_structure(self):
        """Fill blank should map to textQuestion."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        from schemas.export import ExportQuestionFillBlank, ExportOptions
        
        exporter = GoogleFormsExporter()
        
        question = ExportQuestionFillBlank(
            id=uuid4(),
            type="fill_blank",
            question="The capital of France is _____.",
            options=["Paris", "London", "Berlin"],
            correct_answer="Paris"
        )
        options = ExportOptions(include_answer_key=True)
        
        item = exporter._build_fill_blank_item(question, 0, options)
        
        question_item = item["item"]["questionItem"]["question"]
        assert "textQuestion" in question_item
        assert question_item["textQuestion"]["paragraph"] is False  # Short answer
        
        # Check grading - textQuestion does NOT support correctAnswers (API limitation)
        # We use generalFeedback and whenWrong instead for manual grading
        assert "grading" in question_item
        assert question_item["grading"]["pointValue"] == 1
        assert "correctAnswers" not in question_item["grading"]  # Not supported for text
        assert "Paris" in question_item["grading"]["generalFeedback"]["text"]
        assert "Paris" in question_item["grading"]["whenWrong"]["text"]
    
    def test_find_correct_option_index_exact_match(self):
        """Should find exact match in options."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        options = ["Apple", "Banana", "Cherry"]
        
        assert exporter._find_correct_option_index(options, "Banana") == 1
    
    def test_find_correct_option_index_case_insensitive(self):
        """Should find case-insensitive match."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        options = ["Apple", "Banana", "Cherry"]
        
        assert exporter._find_correct_option_index(options, "banana") == 1
        assert exporter._find_correct_option_index(options, "CHERRY") == 2
    
    def test_find_correct_option_index_letter_match(self):
        """Should match letter answers (A, B, C, D)."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        options = ["First", "Second", "Third", "Fourth"]
        
        assert exporter._find_correct_option_index(options, "A") == 0
        assert exporter._find_correct_option_index(options, "B") == 1
        assert exporter._find_correct_option_index(options, "C") == 2
        assert exporter._find_correct_option_index(options, "D") == 3
    
    def test_find_correct_option_index_fallback(self):
        """Should fallback to 0 if no match found."""
        from services.exporters.google_forms_exporter import GoogleFormsExporter
        
        exporter = GoogleFormsExporter()
        options = ["Apple", "Banana", "Cherry"]
        
        assert exporter._find_correct_option_index(options, "NotFound") == 0

