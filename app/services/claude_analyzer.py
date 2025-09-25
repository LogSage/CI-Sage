import anthropic
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)

class ClaudeAnalyzer:
    """Claude AI integration for analyzing GitHub Actions failures"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-3-sonnet-20240229"  # Use Claude 3 Sonnet for analysis
    
    def _generate_error_signature_hash(self, logs: str, error_pattern: str) -> str:
        """Generate a hash for error signature matching"""
        content = f"{logs[:1000]}{error_pattern}"  # Use first 1000 chars + pattern
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_analysis_prompt(self, logs: str, workflow_name: str, artifacts: List[Dict]) -> str:
        """Generate the analysis prompt for Claude"""
        artifacts_info = ""
        if artifacts:
            artifacts_info = f"\n\nArtifacts available:\n"
            for artifact in artifacts:
                artifacts_info += f"- {artifact.get('name', 'Unknown')}: {artifact.get('size_in_bytes', 0)} bytes\n"
        
        prompt = f"""You are an expert DevOps engineer analyzing GitHub Actions workflow failures. Analyze the following workflow logs and provide a comprehensive failure analysis.

Workflow: {workflow_name}
{artifacts_info}

Logs:
{logs}

Please provide your analysis in the following JSON format:
{{
    "failure_reason": "Clear, concise explanation of the root cause",
    "confidence_score": 0.85,
    "remediation_steps": [
        "Step 1: Specific action to take",
        "Step 2: Another specific action",
        "Step 3: Verification step"
    ],
    "error_type": "One of: dependency, permission, timeout, configuration, network, resource, syntax, environment",
    "suggested_labels": ["bug", "ci", "priority-high"],
    "can_auto_fix": false,
    "auto_fix_patch": null
}}

Guidelines:
1. Be specific about the root cause - avoid generic explanations
2. Provide actionable remediation steps
3. Confidence score should be 0.0-1.0 based on how certain you are
4. Error types should be specific categories that can be learned from
5. Only set can_auto_fix to true if you can provide a concrete patch
6. If auto_fix_patch is provided, it should be valid YAML/configuration
7. Suggested labels should be relevant GitHub issue labels

Focus on the most critical failure point and provide the most likely solution."""
        
        return prompt
    
    def _get_remediation_prompt(self, error_type: str, previous_fixes: List[Dict]) -> str:
        """Generate a prompt for remediation suggestions based on error type and history"""
        history_context = ""
        if previous_fixes:
            history_context = f"\n\nPrevious successful fixes for similar errors:\n"
            for fix in previous_fixes[-3:]:  # Last 3 fixes
                history_context += f"- {fix.get('remediation_steps', [])}\n"
        
        prompt = f"""Based on the error type "{error_type}" and previous successful fixes, suggest the most effective remediation approach.

{history_context}

Provide specific, actionable steps that have worked before for this type of error."""
        
        return prompt
    
    async def analyze_workflow_failure(
        self,
        logs: str,
        workflow_name: str,
        artifacts: List[Dict] = None,
        error_history: List[Dict] = None
    ) -> AnalysisResult:
        """Analyze workflow failure and return structured results"""
        try:
            prompt = self._get_analysis_prompt(logs, workflow_name, artifacts or [])
            
            # Use Claude for analysis
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.1,  # Low temperature for consistent analysis
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse the response
            response_text = response.content[0].text
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start != -1 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    analysis_data = json.loads(json_str)
                else:
                    raise ValueError("No JSON found in response")
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse Claude response as JSON: {e}")
                # Fallback to basic analysis
                analysis_data = {
                    "failure_reason": "Analysis failed - unable to parse response",
                    "confidence_score": 0.1,
                    "remediation_steps": ["Review logs manually", "Check workflow configuration"],
                    "error_type": "unknown",
                    "suggested_labels": ["ci", "needs-triage"],
                    "can_auto_fix": False,
                    "auto_fix_patch": None
                }
            
            # Validate and clean the analysis data
            result = AnalysisResult(
                failure_reason=analysis_data.get("failure_reason", "Unknown error"),
                confidence_score=min(max(analysis_data.get("confidence_score", 0.5), 0.0), 1.0),
                remediation_steps=analysis_data.get("remediation_steps", ["Review logs manually"]),
                error_type=analysis_data.get("error_type", "unknown"),
                suggested_labels=analysis_data.get("suggested_labels", ["ci"]),
                can_auto_fix=analysis_data.get("can_auto_fix", False),
                auto_fix_patch=analysis_data.get("auto_fix_patch")
            )
            
            logger.info(f"Analysis completed with confidence: {result.confidence_score}")
            return result
            
        except Exception as e:
            logger.error(f"Error during Claude analysis: {e}")
            # Return fallback analysis
            return AnalysisResult(
                failure_reason=f"Analysis failed: {str(e)}",
                confidence_score=0.1,
                remediation_steps=["Review logs manually", "Check workflow configuration"],
                error_type="unknown",
                suggested_labels=["ci", "needs-triage"],
                can_auto_fix=False,
                auto_fix_patch=None
            )
    
    async def generate_patch(
        self,
        error_type: str,
        workflow_content: str,
        failure_context: str
    ) -> Optional[str]:
        """Generate a patch for auto-fixable issues"""
        try:
            prompt = f"""Generate a patch for a GitHub Actions workflow to fix the following issue:

Error Type: {error_type}
Context: {failure_context}

Current workflow content:
{workflow_content}

Provide ONLY the corrected workflow YAML content, not explanations. The patch should be minimal and focused on fixing the specific issue."""
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            patch = response.content[0].text.strip()
            
            # Basic validation - check if it looks like YAML
            if 'name:' in patch and ('on:' in patch or 'workflow_dispatch:' in patch):
                return patch
            else:
                logger.warning("Generated patch doesn't look like valid workflow YAML")
                return None
                
        except Exception as e:
            logger.error(f"Error generating patch: {e}")
            return None
    
    def generate_error_signature(self, logs: str, error_pattern: str) -> str:
        """Generate a signature hash for error pattern matching"""
        return self._generate_error_signature_hash(logs, error_pattern)

# Global instance
claude_analyzer = ClaudeAnalyzer()
