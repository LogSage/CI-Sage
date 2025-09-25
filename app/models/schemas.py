from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class WorkflowRunEvent(BaseModel):
    """GitHub webhook payload for workflow_run events"""
    action: str
    workflow_run: Dict[str, Any]
    repository: Dict[str, Any]
    organization: Optional[Dict[str, Any]] = None

class AnalysisRequest(BaseModel):
    """Request for workflow analysis"""
    workflow_run_id: int
    repository: str
    workflow_name: str
    logs: str
    artifacts: List[Dict[str, Any]] = []
    status: str

class AnalysisResult(BaseModel):
    """Result of workflow analysis"""
    failure_reason: str
    confidence_score: float
    remediation_steps: List[str]
    error_type: str
    suggested_labels: List[str] = []
    can_auto_fix: bool = False
    auto_fix_patch: Optional[str] = None

class CheckRunOutput(BaseModel):
    """Output for GitHub Check Run"""
    title: str
    summary: str
    text: str

class CheckRunData(BaseModel):
    """Data for creating a GitHub Check Run"""
    name: str
    head_sha: str
    status: str
    conclusion: Optional[str] = None
    output: Optional[CheckRunOutput] = None

class IssueData(BaseModel):
    """Data for creating a GitHub Issue"""
    title: str
    body: str
    labels: List[str] = []

class PullRequestData(BaseModel):
    """Data for creating a GitHub Pull Request"""
    title: str
    head: str
    base: str
    body: str

class ErrorSignatureData(BaseModel):
    """Data for error signature"""
    signature_hash: str
    error_pattern: str
    error_type: str
    confidence_score: float
    remediation_steps: List[str]
    success_rate: float = 0.0
    occurrence_count: int = 1

class WorkflowAnalysisData(BaseModel):
    """Data for workflow analysis storage"""
    workflow_run_id: int
    repository: str
    workflow_name: str
    status: str
    failure_reason: str
    confidence_score: float
    remediation_steps: List[str]
    error_signature_id: Optional[int] = None
    check_run_id: Optional[int] = None
    issue_id: Optional[int] = None
    pr_id: Optional[int] = None
    analysis_prompt: str
    analysis_response: str
