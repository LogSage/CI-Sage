import hmac
import hashlib
import json
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.core.database import get_db
from app.core.config import settings
from app.core.github import github_api
from app.services.claude_analyzer import claude_analyzer
from app.services.learning_system import LearningSystem
from app.models.schemas import WorkflowRunEvent, WorkflowAnalysisData
from app.services.workflow_processor import WorkflowProcessor

logger = logging.getLogger(__name__)

router = APIRouter()

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature.startswith('sha256='):
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle GitHub webhook events"""
    try:
        # Get the raw payload
        payload = await request.body()
        
        # Verify webhook signature
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not verify_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse the payload
        event_data = json.loads(payload)
        event_type = request.headers.get('X-GitHub-Event', '')
        
        logger.info(f"Received GitHub event: {event_type}")
        
        # Handle workflow_run events
        if event_type == 'workflow_run':
            await handle_workflow_run_event(event_data, db)
        
        return JSONResponse(content={"status": "processed"})
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_workflow_run_event(event_data: Dict[str, Any], db: Session):
    """Handle workflow_run webhook events"""
    try:
        workflow_run = event_data.get('workflow_run', {})
        repository = event_data.get('repository', {})
        action = event_data.get('action', '')
        
        # Only process completed workflows
        if action != 'completed':
            logger.info(f"Skipping workflow_run event with action: {action}")
            return
        
        # Only process failed workflows
        conclusion = workflow_run.get('conclusion', '')
        if conclusion not in ['failure', 'cancelled']:
            logger.info(f"Skipping successful workflow_run with conclusion: {conclusion}")
            return
        
        # Extract workflow information
        workflow_run_id = workflow_run.get('id')
        workflow_name = workflow_run.get('name', 'Unknown')
        head_sha = workflow_run.get('head_sha', '')
        repository_name = repository.get('full_name', '')
        installation_id = str(event_data.get('installation', {}).get('id', ''))
        
        if not all([workflow_run_id, head_sha, repository_name, installation_id]):
            logger.error("Missing required workflow_run data")
            return
        
        logger.info(f"Processing failed workflow: {workflow_name} (ID: {workflow_run_id})")
        
        # Process the workflow
        processor = WorkflowProcessor(
            github_api=github_api,
            claude_analyzer=claude_analyzer,
            learning_system=LearningSystem(db)
        )
        
        await processor.process_workflow_failure(
            workflow_run_id=workflow_run_id,
            repository_name=repository_name,
            workflow_name=workflow_name,
            head_sha=head_sha,
            installation_id=installation_id,
            conclusion=conclusion
        )
        
        logger.info(f"Successfully processed workflow_run {workflow_run_id}")
        
    except Exception as e:
        logger.error(f"Error handling workflow_run event: {e}")
        # Don't raise exception to avoid webhook retries for processing errors

@router.get("/webhooks/health")
async def webhook_health():
    """Health check for webhook endpoint"""
    return {"status": "healthy", "endpoint": "webhooks"}

@router.post("/webhooks/test")
async def test_webhook(request: Request):
    """Test endpoint for webhook development"""
    try:
        payload = await request.json()
        logger.info(f"Test webhook received: {payload}")
        return {"status": "test_received", "data": payload}
    except Exception as e:
        logger.error(f"Test webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
