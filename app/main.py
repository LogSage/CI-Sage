from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
import logging

from app.core.config import settings
from app.api.webhooks import router as webhook_router
from app.core.database import init_db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    await init_db()
    yield
    # Shutdown (if needed)
    pass

app = FastAPI(
    title="CI-Sage",
    description="An agentic system that analyzes GitHub Actions failures",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, prefix="/webhooks")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Detailed health check with dependency verification"""
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": None,
        "dependencies": {}
    }
    
    # Check database connectivity
    try:
        from app.core.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["dependencies"]["database"] = {
            "status": "healthy",
            "type": "postgresql"
        }
    except Exception as e:
        health_status["dependencies"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "type": "postgresql"
        }
        health_status["status"] = "degraded"
    
    # Check Claude API configuration
    try:
        from app.core.config import settings
        if settings.has_real_claude_key:
            health_status["dependencies"]["claude"] = {
                "status": "configured",
                "type": "anthropic_api"
            }
        else:
            health_status["dependencies"]["claude"] = {
                "status": "test_mode",
                "type": "anthropic_api"
            }
    except Exception as e:
        health_status["dependencies"]["claude"] = {
            "status": "error",
            "error": str(e),
            "type": "anthropic_api"
        }
    
    # Check GitHub App configuration
    try:
        if settings.is_production:
            health_status["dependencies"]["github_app"] = {
                "status": "configured",
                "type": "github_app"
            }
        else:
            health_status["dependencies"]["github_app"] = {
                "status": "test_mode",
                "type": "github_app"
            }
    except Exception as e:
        health_status["dependencies"]["github_app"] = {
            "status": "error",
            "error": str(e),
            "type": "github_app"
        }
    
    # Add timestamp
    from datetime import datetime
    health_status["timestamp"] = datetime.utcnow().isoformat()
    
    return health_status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.WEBHOOK_PORT,
        reload=settings.APP_ENV == "development"
    )
