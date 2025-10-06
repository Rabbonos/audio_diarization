#!/usr/bin/env python3
"""
Database initialization and management script
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config import settings
from src.models import Base
from src.services.database_service import DatabaseService

def init_database():
    """Initialize database tables"""
    try:
        print("🗄️ Initializing database...")
        print(f"Database URL: {settings.database_url}")
        
        # Initialize database service (this creates tables)
        db_service = DatabaseService()
        
        print("✅ Database initialized successfully!")
        print("📋 Tables created:")
        print("   - transcription_results")
        print("   - api_usage_stats")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def check_database():
    """Check database connection and tables"""
    try:
        print("🔍 Checking database connection...")
        
        db_service = DatabaseService()
        db = db_service.get_db()
        
        # Test query
        result = db.execute("SELECT 1").fetchone()
        db.close()
        
        print("✅ Database connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False

def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "init":
            init_database()
        elif command == "check":
            check_database()
        else:
            print("Unknown command. Use 'init' or 'check'")
            sys.exit(1)
    else:
        print("🚀 Database Management Script")
        print("=" * 40)
        print("Commands:")
        print("  init  - Initialize database tables")
        print("  check - Check database connection")
        print("")
        print("Usage: python init_database.py <command>")

if __name__ == "__main__":
    main()