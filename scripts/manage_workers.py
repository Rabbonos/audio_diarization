#!/usr/bin/env python3
"""
Worker Management Script

This script helps manage the number of RQ workers for parallel processing control.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

def get_project_root():
    """Get the project root directory"""
    current = Path(__file__).resolve()
    # Go up to find docker-compose.yaml
    for parent in current.parents:
        if (parent / "docker-compose.yaml").exists():
            return parent
    raise RuntimeError("Could not find project root (no docker-compose.yaml found)")

def scale_workers(num_workers: int):
    """Scale the number of RQ workers"""
    project_root = get_project_root()
    
    print(f"📊 Scaling workers to {num_workers}...")
    
    try:
        # Change to project directory
        os.chdir(project_root)
        
        # Scale workers using docker-compose
        cmd = ["docker-compose", "up", "-d", "--scale", f"rq_worker={num_workers}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Successfully scaled to {num_workers} workers")
            print("📋 Check status with: docker-compose ps")
        else:
            print(f"❌ Failed to scale workers:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error scaling workers: {e}")
        return False
    
    return True

def get_worker_status():
    """Get current worker status"""
    project_root = get_project_root()
    
    try:
        os.chdir(project_root)
        
        # Get running containers
        cmd = ["docker-compose", "ps", "--filter", "name=rq_worker"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("📊 Current Worker Status:")
            print("=" * 50)
            print(result.stdout)
        else:
            print("❌ Failed to get worker status")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Error getting worker status: {e}")

def stop_all_workers():
    """Stop all workers"""
    project_root = get_project_root()
    
    try:
        os.chdir(project_root)
        
        print("🛑 Stopping all workers...")
        cmd = ["docker-compose", "stop", "rq_worker"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All workers stopped")
        else:
            print("❌ Failed to stop workers")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Error stopping workers: {e}")

def restart_workers():
    """Restart all workers"""
    project_root = get_project_root()
    
    try:
        os.chdir(project_root)
        
        print("🔄 Restarting workers...")
        cmd = ["docker-compose", "restart", "rq_worker"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Workers restarted")
        else:
            print("❌ Failed to restart workers")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ Error restarting workers: {e}")

def show_logs():
    """Show worker logs"""
    project_root = get_project_root()
    
    try:
        os.chdir(project_root)
        
        print("📜 Worker logs (press Ctrl+C to exit):")
        print("=" * 50)
        cmd = ["docker-compose", "logs", "-f", "rq_worker"]
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n👋 Exiting log view")
    except Exception as e:
        print(f"❌ Error showing logs: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Manage RQ workers for audio diarization service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s scale 5          # Scale to 5 workers
  %(prog)s status           # Show current status
  %(prog)s stop             # Stop all workers
  %(prog)s restart          # Restart all workers
  %(prog)s logs             # Show worker logs

Note: This controls the number of parallel requests the system can handle.
Each worker processes one transcription task at a time.
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Scale command
    scale_parser = subparsers.add_parser('scale', help='Scale workers to specified number')
    scale_parser.add_argument('count', type=int, help='Number of workers')
    
    # Status command
    subparsers.add_parser('status', help='Show current worker status')
    
    # Stop command
    subparsers.add_parser('stop', help='Stop all workers')
    
    # Restart command
    subparsers.add_parser('restart', help='Restart all workers')
    
    # Logs command
    subparsers.add_parser('logs', help='Show worker logs')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    print("🎵 Audio Diarization Worker Manager")
    print("=" * 40)
    
    if args.command == 'scale':
        if args.count < 0:
            print("❌ Worker count must be positive")
            sys.exit(1)
        elif args.count == 0:
            print("⚠️  Scaling to 0 workers will stop all processing")
            confirm = input("Continue? (y/N): ").lower().strip()
            if confirm != 'y':
                print("Cancelled")
                return
        elif args.count > 10:
            print("⚠️  High worker count may cause resource issues")
            confirm = input(f"Continue with {args.count} workers? (y/N): ").lower().strip()
            if confirm != 'y':
                print("Cancelled")
                return
        
        scale_workers(args.count)
        
    elif args.command == 'status':
        get_worker_status()
        
    elif args.command == 'stop':
        stop_all_workers()
        
    elif args.command == 'restart':
        restart_workers()
        
    elif args.command == 'logs':
        show_logs()

if __name__ == "__main__":
    main()