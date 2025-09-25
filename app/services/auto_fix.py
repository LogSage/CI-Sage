import logging
from typing import Optional, Dict, Any
import tempfile
import os
import subprocess
from pathlib import Path

from app.core.github import GitHubAPI
from app.services.claude_analyzer import ClaudeAnalyzer

logger = logging.getLogger(__name__)

class AutoFixService:
    """Service for automatically proposing fixes via GitHub PRs"""
    
    def __init__(self, github_api: GitHubAPI, claude_analyzer: ClaudeAnalyzer):
        self.github_api = github_api
        self.claude_analyzer = claude_analyzer
    
    async def propose_workflow_fix(
        self,
        installation_id: str,
        repository_name: str,
        workflow_name: str,
        head_sha: str,
        analysis_result,
        workflow_content: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Propose a fix for a workflow via PR"""
        try:
            if not analysis_result.can_auto_fix:
                logger.info("Analysis indicates this error cannot be auto-fixed")
                return None
            
            owner, repo = repository_name.split('/', 1)
            
            # Get the current workflow content if not provided
            if not workflow_content:
                workflow_content = await self._get_workflow_content(
                    installation_id, owner, repo, workflow_name
                )
            
            if not workflow_content:
                logger.warning("Could not retrieve workflow content")
                return None
            
            # Generate the patch
            patch = await self._generate_workflow_patch(
                analysis_result, workflow_content
            )
            
            if not patch:
                logger.warning("Could not generate valid patch")
                return None
            
            # Create a new branch and PR
            pr = await self._create_fix_pr(
                installation_id, owner, repo, head_sha,
                workflow_name, analysis_result, patch
            )
            
            logger.info(f"Created auto-fix PR: {pr.get('number')}")
            return pr
            
        except Exception as e:
            logger.error(f"Error proposing workflow fix: {e}")
            return None
    
    async def _get_workflow_content(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        workflow_name: str
    ) -> Optional[str]:
        """Get the current workflow file content"""
        try:
            # Try to find the workflow file
            workflow_path = f".github/workflows/{workflow_name}.yml"
            
            response = await self.github_api.make_request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{workflow_path}",
                installation_id
            )
            
            if response.status_code == 200:
                import base64
                content_data = response.json()
                content = base64.b64decode(content_data['content']).decode('utf-8')
                return content
            else:
                # Try .yaml extension
                workflow_path = f".github/workflows/{workflow_name}.yaml"
                response = await self.github_api.make_request(
                    "GET",
                    f"/repos/{owner}/{repo}/contents/{workflow_path}",
                    installation_id
                )
                
                if response.status_code == 200:
                    import base64
                    content_data = response.json()
                    content = base64.b64decode(content_data['content']).decode('utf-8')
                    return content
            
            logger.warning(f"Could not find workflow file for {workflow_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting workflow content: {e}")
            return None
    
    async def _generate_workflow_patch(
        self,
        analysis_result,
        workflow_content: str
    ) -> Optional[str]:
        """Generate a patch for the workflow"""
        try:
            patch = await self.claude_analyzer.generate_patch(
                error_type=analysis_result.error_type,
                workflow_content=workflow_content,
                failure_context=analysis_result.failure_reason
            )
            
            if patch and self._validate_patch(patch):
                return patch
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating workflow patch: {e}")
            return None
    
    def _validate_patch(self, patch: str) -> bool:
        """Validate that the patch is valid YAML"""
        try:
            import yaml
            yaml.safe_load(patch)
            return True
        except yaml.YAMLError:
            logger.warning("Generated patch is not valid YAML")
            return False
    
    async def _create_fix_pr(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        head_sha: str,
        workflow_name: str,
        analysis_result,
        patch: str
    ) -> Dict[str, Any]:
        """Create a PR with the proposed fix"""
        try:
            # Create a new branch name
            branch_name = f"fix/{workflow_name.lower().replace(' ', '-')}-{head_sha[:8]}"
            
            # Get the workflow file path
            workflow_path = f".github/workflows/{workflow_name}.yml"
            
            # Create the branch
            await self._create_branch(
                installation_id, owner, repo, branch_name, head_sha
            )
            
            # Update the workflow file
            await self._update_workflow_file(
                installation_id, owner, repo, branch_name,
                workflow_path, patch
            )
            
            # Create the PR
            pr_title = f"Fix: {workflow_name} - {analysis_result.failure_reason[:80]}"
            pr_body = f"""## Auto-Generated Fix

This PR automatically fixes the following issue in `{workflow_name}`:

**Problem:** {analysis_result.failure_reason}

**Error Type:** {analysis_result.error_type}

**Confidence:** {analysis_result.confidence_score:.1%}

## Changes Made
- Applied automated fix for {analysis_result.error_type} error
- Updated workflow configuration to resolve the issue

## Remediation Steps Applied
{chr(10).join([f"- {step}" for step in analysis_result.remediation_steps])}

## Review Notes
- This fix was generated by CI-Sage
- Please review the changes before merging
- Test the workflow to ensure the fix works as expected

---
*Generated by CI-Sage*"""
            
            pr = await self.github_api.create_pull_request(
                installation_id=installation_id,
                owner=owner,
                repo=repo,
                title=pr_title,
                head=branch_name,
                base="main",  # or get from default branch
                body=pr_body
            )
            
            return pr
            
        except Exception as e:
            logger.error(f"Error creating fix PR: {e}")
            raise
    
    async def _create_branch(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        branch_name: str,
        head_sha: str
    ):
        """Create a new branch"""
        try:
            # Get the default branch first
            repo_info = await self.github_api.make_request(
                "GET",
                f"/repos/{owner}/{repo}",
                installation_id
            )
            
            if repo_info.status_code != 200:
                raise Exception(f"Failed to get repo info: {repo_info.status_code}")
            
            default_branch = repo_info.json().get('default_branch', 'main')
            
            # Create the branch
            branch_data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": head_sha
            }
            
            response = await self.github_api.make_request(
                "POST",
                f"/repos/{owner}/{repo}/git/refs",
                installation_id,
                data=branch_data
            )
            
            if response.status_code not in [201, 422]:  # 422 means branch already exists
                raise Exception(f"Failed to create branch: {response.status_code}")
            
            logger.info(f"Created branch: {branch_name}")
            
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            raise
    
    async def _update_workflow_file(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        branch_name: str,
        workflow_path: str,
        patch: str
    ):
        """Update the workflow file with the patch"""
        try:
            # Get the current file content and SHA
            file_response = await self.github_api.make_request(
                "GET",
                f"/repos/{owner}/{repo}/contents/{workflow_path}",
                installation_id,
                params={"ref": branch_name}
            )
            
            if file_response.status_code != 200:
                raise Exception(f"Failed to get file content: {file_response.status_code}")
            
            file_data = file_response.json()
            current_sha = file_data['sha']
            
            # Encode the new content
            import base64
            encoded_content = base64.b64encode(patch.encode('utf-8')).decode('utf-8')
            
            # Update the file
            update_data = {
                "message": f"Fix workflow: {workflow_path}",
                "content": encoded_content,
                "sha": current_sha,
                "branch": branch_name
            }
            
            response = await self.github_api.make_request(
                "PUT",
                f"/repos/{owner}/{repo}/contents/{workflow_path}",
                installation_id,
                data=update_data
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to update file: {response.status_code}")
            
            logger.info(f"Updated workflow file: {workflow_path}")
            
        except Exception as e:
            logger.error(f"Error updating workflow file: {e}")
            raise
    
    async def get_known_fixes(self, error_type: str) -> list:
        """Get known fixes for a specific error type"""
        # This could be expanded to include a database of known fixes
        known_fixes = {
            "dependency": [
                "Update dependency versions",
                "Add dependency caching",
                "Use specific version pins"
            ],
            "permission": [
                "Add required permissions to workflow",
                "Update GITHUB_TOKEN permissions",
                "Add repository secrets"
            ],
            "timeout": [
                "Increase timeout values",
                "Add retry logic",
                "Optimize workflow steps"
            ],
            "configuration": [
                "Fix YAML syntax errors",
                "Update workflow triggers",
                "Correct environment variables"
            ]
        }
        
        return known_fixes.get(error_type, [])
    
    def can_auto_fix(self, error_type: str, confidence_score: float) -> bool:
        """Determine if an error can be automatically fixed"""
        # Only auto-fix high-confidence, well-known error types
        auto_fixable_types = ["dependency", "permission", "timeout", "configuration"]
        
        return (
            error_type in auto_fixable_types and
            confidence_score > 0.8
        )
