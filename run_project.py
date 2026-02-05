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
import socket

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
    
    # Check Python packages (minimal sanity + known backend deps)
    backend_modules = [
        "uvicorn",
        "fastapi",
        "sqlalchemy",
        "psycopg2",
        "pydantic",
        "pydantic_settings",
        "dotenv",
        "alembic",
        "multipart",
        "reportlab",
    ]
    missing_backend = []
    for module_name in backend_modules:
        try:
            # Handle naming difference for python-multipart
            if module_name == "multipart":
                import multipart
            else:
                __import__(module_name)
        except ImportError:
            missing_backend.append(module_name)

    if missing_backend:
        print(f"   [WARN] Missing backend deps: {', '.join(missing_backend)}")
        print("   [WARN] Installing backend dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=BACKEND_DIR,
            check=True
        )
        print("   [OK] Backend dependencies installed")
    else:
        print("   [OK] Backend dependencies found")
    
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


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if the given TCP port can be bound to (is truly available)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except Exception:
        return False


def find_available_port(start_port: int, max_tries: int = 50) -> int:
    """
    Find an available TCP port starting from start_port.
    Tries up to `max_tries` consecutive ports.
    """
    host = "127.0.0.1"
    for port in range(start_port, start_port + max_tries):
        if is_port_available(port, host):
            return port
    raise RuntimeError(f"No free port found starting from {start_port} (checked {max_tries} ports)")


def start_backend(port: int):
    """Start the FastAPI backend server on the given port."""
    global backend_process
    print(f"[START] Starting Backend Server on http://localhost:{port}")
    print(f"   API Docs: http://localhost:{port}/docs")
    
    # Use CREATE_NEW_PROCESS_GROUP on Windows for better signal handling
    creation_flags = 0
    if IS_WINDOWS:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port), "--reload"],
        cwd=BACKEND_DIR,
        creationflags=creation_flags
    )
    
    return backend_process


def start_frontend(port: int, api_base_url: str):
    """Start the Vite React frontend server, pointing it at the given API base URL."""
    global frontend_process
    print(f"[START] Starting Frontend Server on http://localhost:{port}")
    print(f"   Using API base URL: {api_base_url}")
    
    # Use CREATE_NEW_PROCESS_GROUP on Windows for better signal handling
    creation_flags = 0
    if IS_WINDOWS:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    env = os.environ.copy()
    env["VITE_API_URL"] = api_base_url
    
    # On Windows, we should pass "npm.cmd" if not using shell=True, 
    # but here shell=True is used which should handle it.
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port)],
        cwd=FRONTEND_DIR,
        shell=True,
        creationflags=creation_flags,
        env=env
    )
    
    return frontend_process


def cleanup(signum=None, frame=None):
    """Clean up processes on exit."""
    print("\n\n[STOP] Shutting down servers...")
    
    def kill_process_tree(proc):
        if not proc:
            return
        try:
            if IS_WINDOWS:
                # Use taskkill to kill the process and all its children (/T)
                # /F is force, /T is tree
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], 
                               capture_output=True, check=False)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            print(f"   [WARN] Error killing process {proc.pid}: {e}")

    if backend_process:
        kill_process_tree(backend_process)
        print("   [OK] Backend server stopped")
    
    if frontend_process:
        kill_process_tree(frontend_process)
        print("   [OK] Frontend server stopped")
    
    print("\n[EXIT] Goodbye!\n")
    # Small delay for port release
    time.sleep(1)
    sys.exit(0)


def main():
    """Main entry point."""
    print_banner()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, cleanup)
    if IS_WINDOWS:
        # SIGBREAK is useful on Windows for CTRL+C / CTRL+BREAK
        signal.signal(signal.SIGBREAK, cleanup)
    else:
        signal.signal(signal.SIGTERM, cleanup)
    
    try:
        # Check and install dependencies
        check_requirements()
        
        # Start servers
        # Find a free backend port
        backend_port = find_available_port(BACKEND_PORT)
        if backend_port != BACKEND_PORT:
            print(f"[WARN] Default backend port {BACKEND_PORT} is in use or forbidden.")
            print(f"       Using alternative port {backend_port} instead.")
        
        # Find a free frontend port
        frontend_port = find_available_port(FRONTEND_PORT)
        if frontend_port != FRONTEND_PORT:
            print(f"[WARN] Default frontend port {FRONTEND_PORT} is in use or forbidden.")
            print(f"       Using alternative port {frontend_port} instead.")

        start_backend(backend_port)
        time.sleep(2)  # Wait for backend to start
        
        api_base_url = f"http://127.0.0.1:{backend_port}/api"
        start_frontend(frontend_port, api_base_url)
        time.sleep(3)  # Wait for frontend to start
        
        print("\n" + "=" * 60)
        print("   [OK] All servers are running!")
        print(f"   Frontend: http://localhost:{frontend_port}")
        print(f"   Backend API: http://localhost:{backend_port}")
        print(f"   API Docs: http://localhost:{backend_port}/docs")
        print("=" * 60)
        print("\n   Press Ctrl+C to stop all servers\n")
        
        # Open browser automatically
        webbrowser.open(f"http://localhost:{frontend_port}")
        
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
        print(f"\n[ERROR] critical error: {e}")
        import traceback
        traceback.print_exc()
        cleanup()


if __name__ == "__main__":
    main()
