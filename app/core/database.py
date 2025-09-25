from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(settings.railway_database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Metadata for migrations
metadata = MetaData()

async def init_db():
    """Initialize database tables"""
    try:
        # Import all models to ensure they're registered
        from app.models import ErrorSignature, WorkflowAnalysis, LearningFeedback
        
        # Test database connection first
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        logger.info("App will start without database - add PostgreSQL service in Railway")
        # Don't raise exception - let app start without database

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
