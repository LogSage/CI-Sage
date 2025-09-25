from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Float
from sqlalchemy.sql import func
from app.core.database import Base

class ErrorSignature(Base):
    """Store error signatures for learning and pattern recognition"""
    __tablename__ = "error_signatures"
    
    id = Column(Integer, primary_key=True, index=True)
    signature_hash = Column(String(64), unique=True, index=True)  # Hash of error pattern
    error_pattern = Column(Text)  # The actual error pattern/text
    error_type = Column(String(100))  # Type of error (e.g., "dependency", "permission", "timeout")
    confidence_score = Column(Float)  # Confidence in the analysis
    remediation_steps = Column(JSON)  # Suggested remediation steps
    success_rate = Column(Float, default=0.0)  # Success rate of suggested fixes
    occurrence_count = Column(Integer, default=1)  # How many times this error has been seen
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class WorkflowAnalysis(Base):
    """Store workflow analysis results"""
    __tablename__ = "workflow_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, index=True)
    repository = Column(String(200), index=True)  # owner/repo format
    workflow_name = Column(String(200))
    status = Column(String(50))  # success, failure, cancelled
    failure_reason = Column(Text)  # Root cause analysis
    confidence_score = Column(Float)
    remediation_steps = Column(JSON)
    error_signature_id = Column(Integer)  # Reference to ErrorSignature
    check_run_id = Column(Integer)  # GitHub Check Run ID
    issue_id = Column(Integer)  # GitHub Issue ID (if created)
    pr_id = Column(Integer)  # GitHub PR ID (if created)
    analysis_prompt = Column(Text)  # The prompt used for analysis
    analysis_response = Column(Text)  # Full LLM response
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class LearningFeedback(Base):
    """Store feedback on remediation effectiveness"""
    __tablename__ = "learning_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_analysis_id = Column(Integer, index=True)
    remediation_applied = Column(Boolean)
    success = Column(Boolean)
    feedback_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
