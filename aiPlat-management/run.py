#!/usr/bin/env python3
"""启动脚本 - 同时启动后端和前端"""
import subprocess
import time
import sys

def start_backend():
    """启动后端服务"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "management.server:create_app", 
         "--host", "0.0.0.0", "--port", "8000"],
        cwd="/Users/apple/workdata/person/zy/aiPlatform/aiPlat-management",
        stdout=open("/tmp/aiplat-management.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    return proc

def start_frontend():
    """启动前端服务"""
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="/Users/apple/workdata/person/zy/aiPlatform/aiPlat-management/frontend",
        stdout=open("/tmp/aiplat-frontend.log", "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )
    return proc

if __name__ == "__main__":
    print("Starting backend...")
    backend = start_backend()
    time.sleep(3)
    
    print("Starting frontend...")
    frontend = start_frontend()
    time.sleep(3)
    
    print("\nServices started:")
    print("  Backend: http://localhost:8000")
    print("  Frontend: http://localhost:5173")
    print("\nPress Ctrl+C to stop")
    
    try:
        backend.wait()
    except KeyboardInterrupt:
        backend.terminate()
        frontend.terminate()
        print("\nStopped")