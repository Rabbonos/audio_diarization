#!/usr/bin/env python3
"""
Debug script to inspect Redis and PostgreSQL storage
"""
import redis
import psycopg
from psycopg.rows import dict_row
import json
from datetime import datetime
import os
import sys

# Add src to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from config import settings

# Configuration from settings (adjust for localhost when running outside Docker)
# Parse redis://host:port/db
redis_url = settings.redis_url.replace("redis://redis:", "redis://localhost:")
redis_parts = redis_url.replace("redis://", "").split("/")
redis_host_port = redis_parts[0].split(":")
REDIS_HOST = redis_host_port[0]
REDIS_PORT = int(redis_host_port[1]) if len(redis_host_port) > 1 else 6379
REDIS_DB = int(redis_parts[1]) if len(redis_parts) > 1 else 0

# PostgreSQL config from settings (adjust for localhost and clean URL)
POSTGRES_URL = settings.database_url
POSTGRES_URL = POSTGRES_URL.replace("postgres:5432", "localhost:5432")
POSTGRES_URL = POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://")
POSTGRES_URL = POSTGRES_URL.replace("postgres://", "postgresql://")

def print_section(title):
    """Print a section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def inspect_redis():
    """Inspect Redis keys and data"""
    print_section("REDIS STORAGE")
    
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        
        # Get all keys
        all_keys = r.keys("*")
        print(f"\n📊 Total keys in Redis: {len(all_keys)}")
        
        # Group keys by type
        key_types = {}
        for key in all_keys:
            key_type = key.split(":")[0] if ":" in key else "other"
            key_types[key_type] = key_types.get(key_type, 0) + 1
        
        print("\n📦 Keys by type:")
        for key_type, count in sorted(key_types.items()):
            print(f"   {key_type}: {count}")
        
        # Show task metadata
        print("\n🔍 Task Metadata Keys:")
        task_metadata_keys = [k for k in all_keys if k.startswith("task_metadata:")]
        if task_metadata_keys:
            for key in sorted(task_metadata_keys)[:5]:  # Show first 5
                task_id = key.replace("task_metadata:", "")
                data = r.hgetall(key)
                print(f"\n   Task ID: {task_id}")
                print(f"   Status: {data.get('status', 'N/A')}")
                print(f"   Created: {data.get('created_at', 'N/A')}")
                print(f"   Progress: {data.get('progress', 'N/A')}%")
            if len(task_metadata_keys) > 5:
                print(f"\n   ... and {len(task_metadata_keys) - 5} more task metadata entries")
        else:
            print("   No task metadata found")
        
        # Show transcription results
        print("\n📄 Transcription Result Keys:")
        result_keys = [k for k in all_keys if k.startswith("transcription_result:")]
        if result_keys:
            for key in sorted(result_keys)[:3]:  # Show first 3
                task_id = key.replace("transcription_result:", "")
                data = r.get(key)
                if data:
                    try:
                        result = json.loads(data)
                        print(f"\n   Task ID: {task_id}")
                        print(f"   Status: {result.get('status', 'N/A')}")
                        text = result.get('transcription_text', '')
                        print(f"   Text: {text[:100]}..." if len(text) > 100 else f"   Text: {text}")
                    except:
                        print(f"\n   Task ID: {task_id} (unable to parse)")
            if len(result_keys) > 3:
                print(f"\n   ... and {len(result_keys) - 3} more transcription results")
        else:
            print("   No transcription results found")
        
        # Show RQ job keys
        print("\n⚙️  RQ Job Keys:")
        rq_job_keys = [k for k in all_keys if k.startswith("rq:job:")]
        print(f"   Total RQ jobs: {len(rq_job_keys)}")
        if rq_job_keys:
            for key in sorted(rq_job_keys)[:3]:
                job_id = key.replace("rq:job:", "")
                print(f"   - {job_id}")
            if len(rq_job_keys) > 3:
                print(f"   ... and {len(rq_job_keys) - 3} more jobs")
        
        # Show RQ queues
        print("\n📋 RQ Queues:")
        queue_keys = [k for k in all_keys if k.startswith("rq:queue:")]
        for key in queue_keys:
            queue_name = key.replace("rq:queue:", "")
            queue_length = r.llen(key)
            print(f"   {queue_name}: {queue_length} jobs")
        
        print("\n✅ Redis inspection complete")
        
    except Exception as e:
        print(f"\n❌ Error inspecting Redis: {e}")

def inspect_postgresql():
    """Inspect PostgreSQL tables and data"""
    print_section("POSTGRESQL STORAGE")
    
    try:
        # Use the connection string from settings
        conn = psycopg.connect(POSTGRES_URL)
        cur = conn.cursor(row_factory=dict_row)
        
        # Get table list
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        tables = [row['table_name'] for row in cur.fetchall()]
        print(f"\n📊 Tables in database: {', '.join(tables)}")
        
        # Inspect transcription_results table
        if 'transcription_results' in tables:
            print("\n� Transcription Results Table:")
            cur.execute("SELECT COUNT(*) as count FROM transcription_results")
            count = cur.fetchone()['count']
            print(f"   Total results stored: {count}")
            
            if count > 0:
                cur.execute("""
                    SELECT 
                        task_id,
                        transcription_text,
                        language,
                        status,
                        model,
                        original_filename,
                        word_count,
                        audio_duration_seconds,
                        created_at,
                        completed_at
                    FROM transcription_results 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """)
                results = cur.fetchall()
                
                print("\n   📋 Recent results:")
                for i, result in enumerate(results, 1):
                    text = result['transcription_text'] or ''
                    print(f"\n   {i}. Task ID: {result['task_id']}")
                    print(f"      Status: {result['status']}")
                    print(f"      File: {result['original_filename']}")
                    print(f"      Model: {result['model']} | Language: {result['language']}")
                    print(f"      Duration: {result['audio_duration_seconds']}s | Words: {result['word_count']}")
                    print(f"      Text length: {len(text)} chars")
                    print(f"      Text preview: {text[:80]}..." if len(text) > 80 else f"      Text: {text}")
                    print(f"      Created: {result['created_at']}")
                    if result['completed_at']:
                        print(f"      Completed: {result['completed_at']}")
        
        # Inspect api_usage_stats table
        if 'api_usage_stats' in tables:
            print("\n\n📊 API Usage Stats Table:")
            cur.execute("SELECT COUNT(*) as count FROM api_usage_stats")
            count = cur.fetchone()['count']
            print(f"   Total API usage records: {count}")
            
            if count > 0:
                cur.execute("""
                    SELECT 
                        api_token,
                        endpoint,
                        COUNT(*) as request_count,
                        MAX(created_at) as last_request
                    FROM api_usage_stats 
                    GROUP BY api_token, endpoint
                    ORDER BY request_count DESC
                    LIMIT 5
                """)
                stats = cur.fetchall()
                
                print("\n   📋 Top API usage:")
                for i, stat in enumerate(stats, 1):
                    print(f"\n   {i}. Token: {stat['api_token'][:20]}...")
                    print(f"      Endpoint: {stat['endpoint']}")
                    print(f"      Requests: {stat['request_count']}")
                    print(f"      Last request: {stat['last_request']}")
        
        print("\n✅ PostgreSQL inspection complete")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error inspecting PostgreSQL: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function"""
    print("\n" + "🔍 STORAGE DEBUG TOOL" + "\n")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Inspect both storage systems
    inspect_redis()
    inspect_postgresql()
    
    print("\n" + "="*80)
    print("✅ Inspection complete!")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
