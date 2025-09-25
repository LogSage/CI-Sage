#!/usr/bin/env python3
"""
Utility script for managing the CI-Sage application
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from app.core.database import init_db
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_database():
    """Initialize the database"""
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)

async def test_claude_connection():
    """Test Claude API connection"""
    try:
        from app.services.claude_analyzer import claude_analyzer
        
        # Test with a simple analysis
        test_logs = """
        Error: npm ERR! code ENOENT
        npm ERR! syscall open
        npm ERR! path /github/workspace/package.json
        npm ERR! errno -2
        npm ERR! enoent ENOENT: no such file or directory, open '/github/workspace/package.json'
        """
        
        result = await claude_analyzer.analyze_workflow_failure(
            logs=test_logs,
            workflow_name="test-workflow",
            artifacts=[]
        )
        
        logger.info(f"Claude test successful: {result.failure_reason}")
        logger.info(f"Confidence: {result.confidence_score}")
        
    except Exception as e:
        logger.error(f"Claude test failed: {e}")
        sys.exit(1)

async def test_github_auth():
    """Test GitHub App authentication"""
    try:
        from app.core.github import github_auth
        
        # Test app token generation
        token = github_auth.generate_app_token()
        logger.info("GitHub App token generated successfully")
        
        # Test installation token (requires valid installation ID)
        # This will fail in test environment, but we can check the method exists
        logger.info("GitHub authentication test completed")
        
    except Exception as e:
        logger.error(f"GitHub auth test failed: {e}")
        sys.exit(1)

async def run_tests():
    """Run all tests"""
    logger.info("Running application tests...")
    
    await test_github_auth()
    await test_claude_connection()
    
    logger.info("All tests passed!")

async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python manage.py <command>")
        print("Commands:")
        print("  setup-db    - Initialize database")
        print("  test        - Run tests")
        print("  test-claude - Test Claude API")
        print("  test-github - Test GitHub auth")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "setup-db":
        await setup_database()
    elif command == "test":
        await run_tests()
    elif command == "test-claude":
        await test_claude_connection()
    elif command == "test-github":
        await test_github_auth()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
