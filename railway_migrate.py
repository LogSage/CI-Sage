#!/usr/bin/env python3
"""
One-time migration script for Railway deployment
Run this script to update database schema
"""

import os
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.models.database import Base

def main():
    """Run database migration"""
    print("🚀 Starting CI-Sage database migration...")
    
    try:
        # Create engine
        engine = create_engine(settings.railway_database_url)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                print("📋 Checking current schema...")
                
                # Check if tables exist
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """))
                existing_tables = [row[0] for row in result]
                print(f"Found tables: {existing_tables}")
                
                if existing_tables:
                    print("🗑️ Dropping existing tables...")
                    # Drop in reverse order to handle foreign keys
                    conn.execute(text("DROP TABLE IF EXISTS learning_feedback CASCADE"))
                    conn.execute(text("DROP TABLE IF EXISTS workflow_analyses CASCADE"))
                    conn.execute(text("DROP TABLE IF EXISTS error_signatures CASCADE"))
                    print("✅ Tables dropped successfully")
                
                print("🏗️ Creating new tables with BigInteger columns...")
                # Create all tables with new schema
                Base.metadata.create_all(bind=engine)
                print("✅ Tables created successfully")
                
                # Verify the new schema
                result = conn.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'workflow_analyses' 
                    AND column_name IN ('workflow_run_id', 'check_run_id', 'issue_id', 'pr_id')
                """))
                
                print("📊 New schema verification:")
                for row in result:
                    print(f"  {row[0]}: {row[1]}")
                
                # Commit transaction
                trans.commit()
                print("🎉 Database migration completed successfully!")
                print("✅ CI-Sage is ready to store workflow analysis data!")
                
            except Exception as e:
                trans.rollback()
                print(f"❌ Migration failed: {e}")
                sys.exit(1)
                
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Make sure your Railway PostgreSQL service is running")
        sys.exit(1)

if __name__ == "__main__":
    main()
