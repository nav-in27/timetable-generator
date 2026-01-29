"""
AI Dept Timetable Generator - Full Project Runner

This script starts both the backend (FastAPI) and frontend (Vite React) servers.
Run this file to launch the entire application.
"""

import subprocess
import sys
import os
import time
import signal
import threading
import webbrowser
import platform

# Project directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

# Configuration
BACKEND_PORT = 8000
FRONTEND_PORT = 5173

# Global process references
backend_process = None
frontend_process = None

# Detect Windows
IS_WINDOWS = platform.system() == "Windows"


def print_banner():
    """Print a startup banner."""
    print("\n" + "=" * 60)
    print("   [TIMETABLE GENERATOR] AI DEPT")
    print("   Automated Timetable & Teacher Substitution System")
    print("=" * 60 + "\n")


def check_requirements():
    """Check if required dependencies are available."""
    print("[INFO] Checking requirements...")
    
    # Check Python packages
    try:
        import uvicorn
        import fastapi
        print("   [OK] Backend dependencies found")
    except ImportError:
        print("   [WARN] Backend dependencies missing. Installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=BACKEND_DIR,
            check=True
        )
        print("   [OK] Backend dependencies installed")
    
    # Check if node_modules exists for frontend
    node_modules_path = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(node_modules_path):
        print("   [WARN] Frontend dependencies missing. Installing...")
        subprocess.run(
            ["npm", "install"],
            cwd=FRONTEND_DIR,
            shell=True,
            check=True
        )
        print("   [OK] Frontend dependencies installed")
    else:
        print("   [OK] Frontend dependencies found")
    
    print()


def start_backend():
    """Start the FastAPI backend server."""
    global backend_process
    print(f"[START] Starting Backend Server on http://localhost:{BACKEND_PORT}")
    print(f"   API Docs: http://localhost:{BACKEND_PORT}/docs")
    
    # Use CREATE_NEW_PROCESS_GROUP on Windows for better signal handling
    creation_flags = 0
    if IS_WINDOWS:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--reload"],
        cwd=BACKEND_DIR,
        creationflags=creation_flags
    )
    
    return backend_process


def start_frontend():
    """Start the Vite React frontend server."""
    global frontend_process
    print(f"[START] Starting Frontend Server on http://localhost:{FRONTEND_PORT}")
    
    # Use CREATE_NEW_PROCESS_GROUP on Windows for better signal handling
    creation_flags = 0
    if IS_WINDOWS:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=True,
        creationflags=creation_flags
    )
    
    return frontend_process


def cleanup(signum=None, frame=None):
    """Clean up processes on exit."""
    print("\n\n[STOP] Shutting down servers...")
    
    if backend_process:
        try:
            if IS_WINDOWS:
                backend_process.terminate()
            else:
                backend_process.terminate()
            backend_process.wait(timeout=5)
            print("   [OK] Backend server stopped")
        except Exception as e:
            backend_process.kill()
            print(f"   [WARN] Backend server force killed: {e}")
    
    if frontend_process:
        try:
            if IS_WINDOWS:
                frontend_process.terminate()
            else:
                frontend_process.terminate()
            frontend_process.wait(timeout=5)
            print("   [OK] Frontend server stopped")
        except Exception as e:
            frontend_process.kill()
            print(f"   [WARN] Frontend server force killed: {e}")
    
    print("\n[EXIT] Goodbye!\n")
    sys.exit(0)


def main():
    """Main entry point."""
    print_banner()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, cleanup)
    # SIGTERM is not available on Windows, use SIGBREAK instead
    if IS_WINDOWS:
        signal.signal(signal.SIGBREAK, cleanup)
    else:
        signal.signal(signal.SIGTERM, cleanup)
    
    try:
        # Check and install dependencies
        check_requirements()
        
        # Start servers
        start_backend()
        time.sleep(2)  # Wait for backend to start
        
        start_frontend()
        time.sleep(3)  # Wait for frontend to start
        
        print("\n" + "=" * 60)
        print("   [OK] All servers are running!")
        print(f"   Frontend: http://localhost:{FRONTEND_PORT}")
        print(f"   Backend API: http://localhost:{BACKEND_PORT}")
        print(f"   API Docs: http://localhost:{BACKEND_PORT}/docs")
        print("=" * 60)
        print("\n   Press Ctrl+C to stop all servers\n")
        
        # Open browser automatically
        webbrowser.open(f"http://localhost:{FRONTEND_PORT}")
        
        # Keep the main thread alive
        while True:
            # Check if processes are still running
            if backend_process and backend_process.poll() is not None:
                print("\n[WARN] Backend server stopped unexpectedly!")
                break
            if frontend_process and frontend_process.poll() is not None:
                print("\n[WARN] Frontend server stopped unexpectedly!")
                break
            time.sleep(1)
            
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        cleanup()


if __name__ == "__main__":
    main()
