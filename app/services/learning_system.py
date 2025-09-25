from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
import json
import logging
from app.models.database import ErrorSignature, WorkflowAnalysis
from app.models.schemas import ErrorSignatureData, WorkflowAnalysisData

logger = logging.getLogger(__name__)

class LearningSystem:
    """Manages error signature learning and pattern recognition"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def store_error_signature(
        self,
        signature_hash: str,
        error_pattern: str,
        error_type: str,
        confidence_score: float,
        remediation_steps: List[str],
        success_rate: float = 0.0
    ) -> ErrorSignature:
        """Store or update an error signature"""
        try:
            # Check if signature already exists
            existing = self.db.query(ErrorSignature).filter(
                ErrorSignature.signature_hash == signature_hash
            ).first()
            
            if existing:
                # Update existing signature
                existing.occurrence_count += 1
                existing.confidence_score = max(existing.confidence_score, confidence_score)
                existing.success_rate = success_rate
                existing.remediation_steps = remediation_steps
                self.db.commit()
                logger.info(f"Updated error signature: {signature_hash}")
                return existing
            else:
                # Create new signature
                new_signature = ErrorSignature(
                    signature_hash=signature_hash,
                    error_pattern=error_pattern,
                    error_type=error_type,
                    confidence_score=confidence_score,
                    remediation_steps=remediation_steps,
                    success_rate=success_rate,
                    occurrence_count=1
                )
                self.db.add(new_signature)
                self.db.commit()
                logger.info(f"Created new error signature: {signature_hash}")
                return new_signature
                
        except Exception as e:
            logger.error(f"Error storing error signature: {e}")
            self.db.rollback()
            raise
    
    def find_similar_signatures(
        self,
        error_type: str,
        limit: int = 5
    ) -> List[ErrorSignature]:
        """Find similar error signatures by type"""
        try:
            signatures = self.db.query(ErrorSignature).filter(
                ErrorSignature.error_type == error_type
            ).order_by(
                ErrorSignature.success_rate.desc(),
                ErrorSignature.occurrence_count.desc()
            ).limit(limit).all()
            
            return signatures
            
        except Exception as e:
            logger.error(f"Error finding similar signatures: {e}")
            return []
    
    def get_successful_remediations(
        self,
        error_type: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Get successful remediation steps for error type"""
        try:
            signatures = self.db.query(ErrorSignature).filter(
                and_(
                    ErrorSignature.error_type == error_type,
                    ErrorSignature.success_rate > 0.5
                )
            ).order_by(
                ErrorSignature.success_rate.desc()
            ).limit(limit).all()
            
            remediations = []
            for sig in signatures:
                remediations.append({
                    "remediation_steps": sig.remediation_steps,
                    "success_rate": sig.success_rate,
                    "occurrence_count": sig.occurrence_count
                })
            
            return remediations
            
        except Exception as e:
            logger.error(f"Error getting successful remediations: {e}")
            return []
    
    def store_workflow_analysis(
        self,
        analysis_data: WorkflowAnalysisData,
        error_signature_id: Optional[int] = None
    ) -> WorkflowAnalysis:
        """Store workflow analysis results"""
        try:
            analysis = WorkflowAnalysis(
                workflow_run_id=analysis_data.workflow_run_id,
                repository=analysis_data.repository,
                workflow_name=analysis_data.workflow_name,
                status=analysis_data.status,
                failure_reason=analysis_data.failure_reason,
                confidence_score=analysis_data.confidence_score,
                remediation_steps=analysis_data.remediation_steps,
                error_signature_id=error_signature_id,
                check_run_id=analysis_data.check_run_id,
                issue_id=analysis_data.issue_id,
                pr_id=analysis_data.pr_id,
                analysis_prompt=analysis_data.analysis_prompt,
                analysis_response=analysis_data.analysis_response
            )
            
            self.db.add(analysis)
            self.db.commit()
            logger.info(f"Stored workflow analysis for run {analysis_data.workflow_run_id}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error storing workflow analysis: {e}")
            self.db.rollback()
            raise
    
    def update_analysis_with_github_ids(
        self,
        analysis_id: int,
        check_run_id: Optional[int] = None,
        issue_id: Optional[int] = None,
        pr_id: Optional[int] = None
    ):
        """Update analysis with GitHub resource IDs"""
        try:
            analysis = self.db.query(WorkflowAnalysis).filter(
                WorkflowAnalysis.id == analysis_id
            ).first()
            
            if analysis:
                if check_run_id:
                    analysis.check_run_id = check_run_id
                if issue_id:
                    analysis.issue_id = issue_id
                if pr_id:
                    analysis.pr_id = pr_id
                
                self.db.commit()
                logger.info(f"Updated analysis {analysis_id} with GitHub IDs")
            
        except Exception as e:
            logger.error(f"Error updating analysis with GitHub IDs: {e}")
            self.db.rollback()
    
    def get_analysis_history(
        self,
        repository: str,
        limit: int = 10
    ) -> List[WorkflowAnalysis]:
        """Get analysis history for a repository"""
        try:
            analyses = self.db.query(WorkflowAnalysis).filter(
                WorkflowAnalysis.repository == repository
            ).order_by(
                WorkflowAnalysis.created_at.desc()
            ).limit(limit).all()
            
            return analyses
            
        except Exception as e:
            logger.error(f"Error getting analysis history: {e}")
            return []
    
    def update_signature_success_rate(
        self,
        signature_id: int,
        success: bool
    ):
        """Update success rate for an error signature"""
        try:
            signature = self.db.query(ErrorSignature).filter(
                ErrorSignature.id == signature_id
            ).first()
            
            if signature:
                # Simple moving average for success rate
                total_attempts = signature.occurrence_count
                current_successes = signature.success_rate * total_attempts
                
                if success:
                    new_successes = current_successes + 1
                else:
                    new_successes = current_successes
                
                signature.success_rate = new_successes / (total_attempts + 1)
                signature.occurrence_count += 1
                
                self.db.commit()
                logger.info(f"Updated signature {signature_id} success rate: {signature.success_rate}")
            
        except Exception as e:
            logger.error(f"Error updating signature success rate: {e}")
            self.db.rollback()
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        try:
            total_signatures = self.db.query(ErrorSignature).count()
            total_analyses = self.db.query(WorkflowAnalysis).count()
            
            # Get error type distribution
            error_types = self.db.query(ErrorSignature.error_type).distinct().all()
            type_counts = {}
            for error_type, in error_types:
                count = self.db.query(ErrorSignature).filter(
                    ErrorSignature.error_type == error_type
                ).count()
                type_counts[error_type] = count
            
            return {
                "total_signatures": total_signatures,
                "total_analyses": total_analyses,
                "error_type_distribution": type_counts,
                "average_confidence": self.db.query(WorkflowAnalysis).with_entities(
                    WorkflowAnalysis.confidence_score
                ).all()
            }
            
        except Exception as e:
            logger.error(f"Error getting error statistics: {e}")
            return {}
