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
    """Handle GitHub webhook events with detailed step logging"""
    logger.info("WEBHOOK RECEIVED: Starting GitHub webhook processing")
    
    try:
        # Step 1: Get raw payload
        logger.info("STEP 1: Extracting webhook payload")
        payload = await request.body()
        logger.info(f"Payload size: {len(payload)} bytes")
        
        # Step 2: Verify webhook signature
        logger.info("STEP 2: Verifying webhook signature")
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not verify_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature - rejecting request")
            raise HTTPException(status_code=401, detail="Invalid signature")
        logger.info("Webhook signature verified successfully")
        
        # Step 3: Parse payload
        logger.info("STEP 3: Parsing webhook payload")
        event_data = json.loads(payload)
        event_type = request.headers.get('X-GitHub-Event', '')
        logger.info(f"Event type: {event_type}")
        
        # Step 4: Process event
        logger.info(f"STEP 4: Processing {event_type} event")
        if event_type == 'workflow_run':
            await handle_workflow_run_event(event_data, db)
        else:
            logger.info(f"Skipping non-workflow event: {event_type}")
        
        logger.info("WEBHOOK PROCESSING COMPLETED SUCCESSFULLY")
        return JSONResponse(content={"status": "processed", "event_type": event_type})
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def handle_workflow_run_event(event_data: Dict[str, Any], db: Session):
    """Handle workflow_run webhook events with detailed step logging"""
    logger.info("WORKFLOW RUN EVENT: Starting workflow analysis")
    
    try:
        # Step 1: Extract event data
        logger.info("STEP 1: Extracting workflow run data")
        workflow_run = event_data.get('workflow_run', {})
        repository = event_data.get('repository', {})
        action = event_data.get('action', '')
        
        logger.info(f"Action: {action}")
        logger.info(f"Repository: {repository.get('full_name', 'Unknown')}")
        
        # Step 2: Check if workflow is completed
        logger.info("STEP 2: Checking workflow completion status")
        if action != 'completed':
            logger.info(f"Skipping workflow_run event with action: {action}")
            return
        logger.info("Workflow is completed")
        
        # Step 3: Check if workflow failed
        logger.info("STEP 3: Checking workflow conclusion")
        conclusion = workflow_run.get('conclusion', '')
        logger.info(f"Conclusion: {conclusion}")
        
        if conclusion not in ['failure', 'cancelled']:
            logger.info(f"Skipping successful workflow_run with conclusion: {conclusion}")
            return
        logger.info("Workflow failed - proceeding with analysis")
        
        # Step 4: Extract workflow information
        logger.info("STEP 4: Extracting workflow details")
        workflow_run_id = workflow_run.get('id')
        workflow_name = workflow_run.get('name', 'Unknown')
        head_sha = workflow_run.get('head_sha', '')
        repository_name = repository.get('full_name', '')
        installation_id = str(event_data.get('installation', {}).get('id', ''))
        
        logger.info(f"Workflow ID: {workflow_run_id}")
        logger.info(f"Workflow Name: {workflow_name}")
        logger.info(f"Repository: {repository_name}")
        logger.info(f"Head SHA: {head_sha[:8]}...")
        logger.info(f"Installation ID: {installation_id}")
        
        if not all([workflow_run_id, head_sha, repository_name, installation_id]):
            logger.error("Missing required workflow_run data")
            return
        
        # Step 5: Initialize processors
        logger.info("STEP 5: Initializing AI processors")
        processor = WorkflowProcessor(
            github_api=github_api,
            claude_analyzer=claude_analyzer,
            learning_system=LearningSystem(db)
        )
        logger.info("Processors initialized successfully")
        
        # Step 6: Process workflow failure with AI analysis
        logger.info("STEP 6: Starting AI-powered workflow analysis")
        logger.info(f"Analyzing failed workflow: {workflow_name} (ID: {workflow_run_id})")
        
        await processor.process_workflow_failure(
            workflow_run_id=workflow_run_id,
            repository_name=repository_name,
            workflow_name=workflow_name,
            head_sha=head_sha,
            installation_id=installation_id,
            conclusion=conclusion
        )
        
        logger.info("WORKFLOW ANALYSIS COMPLETED SUCCESSFULLY")
        logger.info(f"Successfully processed workflow_run {workflow_run_id}")
        
    except Exception as e:
        logger.error(f"Error handling workflow_run event: {e}")
        logger.error(f"Workflow ID: {workflow_run.get('id', 'Unknown')}")
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
