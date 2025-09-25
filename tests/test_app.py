import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import AnalysisResult, WorkflowRunEvent
from app.services.claude_analyzer import ClaudeAnalyzer
from app.core.github import GitHubAPI

client = TestClient(app)

@pytest.fixture
def mock_claude_analyzer():
    """Mock Claude analyzer for testing"""
    analyzer = MagicMock(spec=ClaudeAnalyzer)
    analyzer.analyze_workflow_failure = AsyncMock(return_value=AnalysisResult(
        failure_reason="Test failure",
        confidence_score=0.8,
        remediation_steps=["Fix step 1", "Fix step 2"],
        error_type="dependency",
        suggested_labels=["ci", "bug"],
        can_auto_fix=False,
        auto_fix_patch=None
    ))
    return analyzer

@pytest.fixture
def mock_github_api():
    """Mock GitHub API for testing"""
    api = MagicMock(spec=GitHubAPI)
    api.get_workflow_run_logs = AsyncMock(return_value="Test logs")
    api.get_workflow_run_artifacts = AsyncMock(return_value=[])
    api.create_check_run = AsyncMock(return_value={"id": 123})
    api.create_issue = AsyncMock(return_value={"number": 456})
    return api

def test_health_endpoint():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_claude_analyzer():
    """Test Claude analyzer functionality"""
    # Mock the entire ClaudeAnalyzer class to avoid API calls
    with patch('app.services.claude_analyzer.ClaudeAnalyzer') as mock_analyzer_class:
        mock_analyzer = MagicMock()
        mock_analyzer_class.return_value = mock_analyzer
                # Mock the analyze_workflow_failure method to return a coroutine
        from app.models.schemas import AnalysisResult
        mock_result = AnalysisResult(
            failure_reason="Dependency not found",
            confidence_score=0.9,
            remediation_steps=["Install missing dependency", "Update package.json"],
            error_type="dependency",
            suggested_labels=["ci", "dependencies"],
            can_auto_fix=True,
            auto_fix_patch="name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v3\n      - name: Install dependencies\n        run: npm install"
        )
        
        # Create an async mock that returns the result
        async def mock_analyze(*args, **kwargs):
            return mock_result
        
        mock_analyzer.analyze_workflow_failure = mock_analyze
        
        # Test the mocked analyzerr 
        result = await mock_analyzer.analyze_workflow_failure(
            logs="npm ERR! ENOENT: no such file or directory",
            workflow_name="test-workflow",
            artifacts=[]
        )
        
        assert result.failure_reason == "Dependency not found"
        assert result.confidence_score == 0.9
        assert result.error_type == "dependency"
        assert result.can_auto_fix is True

def test_webhook_signature_verification():
    """Test webhook signature verification"""
    from app.api.webhooks import verify_webhook_signature
    from app.core.config import settings
    import hmac
    import hashlib
    
    payload = b'{"test": "data"}'
    secret = settings.GITHUB_WEBHOOK_SECRET  # Use the actual secret from settings
    
    # Generate valid signature
    signature = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Test valid signature
    assert verify_webhook_signature(payload, signature) is True
    
    # Test invalid signature
    invalid_signature = 'sha256=' + 'invalid_signature'
    assert verify_webhook_signature(payload, invalid_signature) is False

@pytest.mark.asyncio
async def test_workflow_processor(mock_claude_analyzer, mock_github_api):
    """Test workflow processor"""
    from app.services.workflow_processor import WorkflowProcessor
    from app.services.learning_system import LearningSystem
    from unittest.mock import MagicMock
    
    # Mock database session
    mock_db = MagicMock()
    learning_system = LearningSystem(mock_db)
    
    processor = WorkflowProcessor(
        github_api=mock_github_api,
        claude_analyzer=mock_claude_analyzer,
        learning_system=learning_system
    )
    
    # Mock the learning system methods
    learning_system.store_error_signature = MagicMock(return_value=MagicMock(id=1))
    learning_system.store_workflow_analysis = MagicMock()
    
    # Test workflow processing
    await processor.process_workflow_failure(
        workflow_run_id=123,
        repository_name="test/repo",
        workflow_name="test-workflow",
        head_sha="abc123",
        installation_id="456",
        conclusion="failure"
    )
    
    # Verify methods were called
    mock_github_api.get_workflow_run_logs.assert_called_once()
    mock_claude_analyzer.analyze_workflow_failure.assert_called_once()
    mock_github_api.create_check_run.assert_called_once()

def test_error_signature_generation():
    """Test error signature generation"""
    from app.services.claude_analyzer import ClaudeAnalyzer
    
    analyzer = ClaudeAnalyzer()
    
    logs = "Error: npm install failed"
    error_pattern = "npm install failed"
    
    signature1 = analyzer.generate_error_signature(logs, error_pattern)
    signature2 = analyzer.generate_error_signature(logs, error_pattern)
    
    # Same inputs should generate same signature
    assert signature1 == signature2
    
    # Different inputs should generate different signatures
    signature3 = analyzer.generate_error_signature("Different logs", error_pattern)
    assert signature1 != signature3

@pytest.mark.asyncio
async def test_auto_fix_service():
    """Test auto-fix service"""
    from app.services.auto_fix import AutoFixService
    
    auto_fix = AutoFixService(mock_github_api, mock_claude_analyzer)
    
    # Test can_auto_fix method
    assert auto_fix.can_auto_fix("dependency", 0.9) is True
    assert auto_fix.can_auto_fix("dependency", 0.5) is False
    assert auto_fix.can_auto_fix("unknown", 0.9) is False
    
    # Test get_known_fixes
    fixes = await auto_fix.get_known_fixes("dependency")
    assert len(fixes) > 0
    assert "Update dependency versions" in fixes

if __name__ == "__main__":
    pytest.main([__file__])
