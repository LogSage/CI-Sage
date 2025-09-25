import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.core.github import GitHubAPI
from app.services.claude_analyzer import ClaudeAnalyzer
from app.services.learning_system import LearningSystem
from app.models.schemas import WorkflowAnalysisData, CheckRunOutput, IssueData

logger = logging.getLogger(__name__)

class WorkflowProcessor:
    """Orchestrates the workflow failure analysis pipeline"""
    
    def __init__(
        self,
        github_api: GitHubAPI,
        claude_analyzer: ClaudeAnalyzer,
        learning_system: LearningSystem
    ):
        self.github_api = github_api
        self.claude_analyzer = claude_analyzer
        self.learning_system = learning_system
    
    async def process_workflow_failure(
        self,
        workflow_run_id: int,
        repository_name: str,
        workflow_name: str,
        head_sha: str,
        installation_id: str,
        conclusion: str
    ):
        """Process a failed workflow run through the complete pipeline"""
        try:
            logger.info(f"WORKFLOW PROCESSOR: Starting analysis for workflow {workflow_run_id}")
            logger.info(f"WORKFLOW PROCESSOR: Repository: {repository_name}")
            logger.info(f"WORKFLOW PROCESSOR: Installation ID: {installation_id}")
            
            # Step 1: Fetch logs and artifacts
            logger.info("WORKFLOW PROCESSOR: STEP 1 - Fetching workflow data from GitHub")
            logs, artifacts = await self._fetch_workflow_data(
                installation_id, repository_name, workflow_run_id
            )
            
            if not logs:
                logger.warning(f"WORKFLOW PROCESSOR: No logs found for workflow {workflow_run_id}")
                logger.warning("WORKFLOW PROCESSOR: Cannot proceed without logs - skipping analysis")
                return
            
            logger.info(f"WORKFLOW PROCESSOR: Successfully fetched {len(logs)} characters of logs")
            
            # Step 2: Analyze with Claude
            logger.info("WORKFLOW PROCESSOR: STEP 2 - Analyzing with Claude AI")
            analysis_result = await self._analyze_with_claude(
                logs, workflow_name, artifacts
            )
            logger.info(f"WORKFLOW PROCESSOR: Claude analysis completed - confidence: {analysis_result.confidence_score}")
            
            # Step 3: Store error signature for learning
            logger.info("WORKFLOW PROCESSOR: STEP 3 - Storing error signature in database")
            error_signature = await self._store_error_signature(
                logs, analysis_result
            )
            logger.info(f"WORKFLOW PROCESSOR: Error signature stored with ID: {error_signature.id}")
            
            # Step 4: Create GitHub Check Run
            logger.info("WORKFLOW PROCESSOR: STEP 4 - Creating GitHub Check Run")
            check_run = await self._create_check_run(
                installation_id, repository_name, head_sha,
                workflow_name, analysis_result
            )
            logger.info(f"WORKFLOW PROCESSOR: Check run created with ID: {check_run.get('id')}")
            
            # Step 5: Create or update issue (if confidence is high)
            logger.info("WORKFLOW PROCESSOR: STEP 5 - Checking if issue should be created")
            issue_id = None
            if analysis_result.confidence_score > 0.7:
                logger.info("WORKFLOW PROCESSOR: High confidence - creating GitHub issue")
                issue_id = await self._create_or_update_issue(
                    installation_id, repository_name,
                    workflow_name, analysis_result
                )
                logger.info(f"WORKFLOW PROCESSOR: Issue created with ID: {issue_id}")
            else:
                logger.info(f"WORKFLOW PROCESSOR: Low confidence ({analysis_result.confidence_score}) - skipping issue creation")
            
            # Step 6: Store analysis in database
            logger.info("WORKFLOW PROCESSOR: STEP 6 - Storing complete analysis in database")
            await self._store_analysis(
                workflow_run_id, repository_name, workflow_name,
                conclusion, analysis_result, error_signature.id,
                check_run.get('id'), issue_id
            )
            logger.info("WORKFLOW PROCESSOR: Analysis stored in database successfully")
            
            # Step 7: Generate patch if auto-fixable (advanced feature)
            if analysis_result.can_auto_fix and analysis_result.auto_fix_patch:
                logger.info("WORKFLOW PROCESSOR: STEP 7 - Auto-fix available - proposing patch")
                await self._propose_patch(
                    installation_id, repository_name, head_sha,
                    analysis_result
                )
                logger.info("WORKFLOW PROCESSOR: Patch proposed successfully")
            
            logger.info(f"WORKFLOW PROCESSOR: Completed full analysis for workflow {workflow_run_id}")
            
        except Exception as e:
            logger.error(f"WORKFLOW PROCESSOR: Error processing workflow {workflow_run_id}: {e}")
            raise
    
    async def _fetch_workflow_data(
        self,
        installation_id: str,
        repository_name: str,
        workflow_run_id: int
    ) -> tuple[str, list]:
        """Fetch workflow logs and artifacts"""
        try:
            owner, repo = repository_name.split('/', 1)
            
            # Fetch logs
            logs = await self.github_api.get_workflow_run_logs(
                installation_id, owner, repo, workflow_run_id
            )
            
            # Fetch artifacts
            artifacts = await self.github_api.get_workflow_run_artifacts(
                installation_id, owner, repo, workflow_run_id
            )
            
            logger.info(f"Fetched {len(logs)} chars of logs and {len(artifacts)} artifacts")
            return logs, artifacts
            
        except Exception as e:
            logger.error(f"Error fetching workflow data: {e}")
            return "", []
    
    async def _analyze_with_claude(
        self,
        logs: str,
        workflow_name: str,
        artifacts: list
    ):
        """Analyze workflow failure with Claude"""
        try:
            # Get historical successful remediations for context
            error_history = self.learning_system.get_successful_remediations(
                "dependency"  # This could be determined from logs first
            )
            
            analysis_result = await self.claude_analyzer.analyze_workflow_failure(
                logs, workflow_name, artifacts, error_history
            )
            
            logger.info(f"Claude analysis completed with confidence: {analysis_result.confidence_score}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in Claude analysis: {e}")
            # Return fallback analysis
            from app.models.schemas import AnalysisResult
            return AnalysisResult(
                failure_reason=f"Analysis failed: {str(e)}",
                confidence_score=0.1,
                remediation_steps=["Review logs manually"],
                error_type="unknown",
                suggested_labels=["ci", "needs-triage"],
                can_auto_fix=False,
                auto_fix_patch=None
            )
    
    async def _store_error_signature(self, logs: str, analysis_result):
        """Store error signature for learning"""
        try:
            signature_hash = self.claude_analyzer.generate_error_signature(
                logs, analysis_result.failure_reason
            )
            
            error_signature = self.learning_system.store_error_signature(
                signature_hash=signature_hash,
                error_pattern=analysis_result.failure_reason,
                error_type=analysis_result.error_type,
                confidence_score=analysis_result.confidence_score,
                remediation_steps=analysis_result.remediation_steps
            )
            
            logger.info(f"Stored error signature: {signature_hash}")
            return error_signature
            
        except Exception as e:
            logger.error(f"Error storing error signature: {e}")
            # Return a dummy signature
            from app.models.database import ErrorSignature
            return ErrorSignature(id=0)
    
    async def _create_check_run(
        self,
        installation_id: str,
        repository_name: str,
        head_sha: str,
        workflow_name: str,
        analysis_result
    ):
        """Create GitHub Check Run with analysis results"""
        try:
            owner, repo = repository_name.split('/', 1)
            
            # Format remediation steps
            remediation_text = "\n".join([
                f"{i+1}. {step}" for i, step in enumerate(analysis_result.remediation_steps)
            ])
            
            # Create check run output
            output = CheckRunOutput(
                title=f"Workflow Analysis: {workflow_name}",
                summary=f"**Root Cause:** {analysis_result.failure_reason}\n\n**Confidence:** {analysis_result.confidence_score:.1%}",
                text=f"""## Analysis Results

**Workflow:** {workflow_name}
**Error Type:** {analysis_result.error_type}
**Confidence Score:** {analysis_result.confidence_score:.1%}

## Root Cause
{analysis_result.failure_reason}

## Remediation Steps
{remediation_text}

## Suggested Labels
{', '.join(analysis_result.suggested_labels)}

---
*This analysis was generated by CI-Sage*"""
            )
            
            check_run = await self.github_api.create_check_run(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                name=f"Actions Analyzer: {workflow_name}",
                head_sha=head_sha,
                status="completed",
                conclusion="failure",
                output=output.model_dump()
            )
            
            logger.info(f"Created check run: {check_run.get('id')}")
            return check_run
            
        except Exception as e:
            logger.error(f"Error creating check run: {e}")
            return {}
    
    async def _create_or_update_issue(
        self,
        installation_id: str,
        repository_name: str,
        workflow_name: str,
        analysis_result
    ):
        """Create or update GitHub issue"""
        try:
            owner, repo = repository_name.split('/', 1)
            
            # Format remediation steps
            remediation_text = "\n".join([
                f"- [ ] {step}" for step in analysis_result.remediation_steps
            ])
            
            issue_data = IssueData(
                title=f"CI Failure: {workflow_name} - {analysis_result.failure_reason[:100]}",
                body=f"""## Workflow Failure Analysis

**Workflow:** `{workflow_name}`
**Error Type:** {analysis_result.error_type}
**Confidence:** {analysis_result.confidence_score:.1%}

## Root Cause
{analysis_result.failure_reason}

## Remediation Steps
{remediation_text}

## Additional Information
- This issue was automatically created by CI-Sage
- Confidence score: {analysis_result.confidence_score:.1%}
- Error type: {analysis_result.error_type}

---
*Generated by CI-Sage*""",
                labels=analysis_result.suggested_labels + ["ci", "automated"]
            )
            
            issue = await self.github_api.create_issue(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                title=issue_data.title,
                body=issue_data.body,
                labels=issue_data.labels
            )
            
            logger.info(f"Created issue: {issue.get('number')}")
            return issue.get('number')
            
        except Exception as e:
            logger.error(f"Error creating issue: {e}")
            return None
    
    async def _store_analysis(
        self,
        workflow_run_id: int,
        repository_name: str,
        workflow_name: str,
        conclusion: str,
        analysis_result,
        error_signature_id: int,
        check_run_id: Optional[int],
        issue_id: Optional[int]
    ):
        """Store analysis results in database"""
        try:
            analysis_data = WorkflowAnalysisData(
                workflow_run_id=workflow_run_id,
                repository=repository_name,
                workflow_name=workflow_name,
                status=conclusion,
                failure_reason=analysis_result.failure_reason,
                confidence_score=analysis_result.confidence_score,
                remediation_steps=analysis_result.remediation_steps,
                error_signature_id=error_signature_id,
                check_run_id=check_run_id,
                issue_id=issue_id,
                analysis_prompt="",  # Could store the actual prompt used
                analysis_response=""  # Could store the full Claude response
            )
            
            self.learning_system.store_workflow_analysis(analysis_data)
            logger.info(f"Stored analysis for workflow {workflow_run_id}")
            
        except Exception as e:
            logger.error(f"Error storing analysis: {e}")
    
    async def _propose_patch(
        self,
        installation_id: str,
        repository_name: str,
        head_sha: str,
        analysis_result
    ):
        """Propose a patch via PR (advanced feature)"""
        try:
            # This is a placeholder for the advanced auto-fix feature
            # Would involve creating a branch, applying the patch, and creating a PR
            logger.info("Auto-fix patch generation not yet implemented")
            
        except Exception as e:
            logger.error(f"Error proposing patch: {e}")
