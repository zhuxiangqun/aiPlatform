"""
System Info - 获取真实系统信息
"""

import platform
import shutil
from typing import Dict, Any


def get_system_info() -> Dict[str, Any]:
    """获取系统基本信息"""
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
    }


def get_memory_info() -> Dict[str, Any]:
    """获取内存信息"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        used = mem.total - mem.available
        usage_percent = (used / mem.total * 100) if mem.total > 0 else 0
        return {
            "total_bytes": mem.total,
            "used_bytes": used,
            "available_bytes": mem.available,
            "usage_percent": round(usage_percent, 1),
            "swap": {
                "total_bytes": psutil.swap_memory().total,
                "used_bytes": psutil.swap_memory().used,
                "usage_percent": psutil.swap_memory().percent
            }
        }
    except ImportError:
        return {
            "total_bytes": 0,
            "used_bytes": 0,
            "available_bytes": 0,
            "usage_percent": 0,
            "swap": {
                "total_bytes": 0,
                "used_bytes": 0,
                "usage_percent": 0
            },
            "error": "psutil not installed"
        }


def get_storage_info() -> Dict[str, Any]:
    """获取存储信息"""
    try:
        total, used, free = shutil.disk_usage('/')
        usage_percent = (used / total * 100) if total > 0 else 0
        return {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": free,
            "usage_percent": round(usage_percent, 1)
        }
    except Exception:
        return {
            "total_bytes": 0,
            "used_bytes": 0,
            "available_bytes": 0,
            "usage_percent": 0,
            "error": "Could not get disk usage"
        }


def get_cpu_info() -> Dict[str, Any]:
    """获取CPU信息"""
    try:
        import psutil
        return {
            "count_physical": psutil.cpu_count(logical=False),
            "count_logical": psutil.cpu_count(logical=True),
            "usage_percent": psutil.cpu_percent(interval=0.1),
            "load_avg": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else [0, 0, 0]
        }
    except ImportError:
        return {
            "count_physical": 0,
            "count_logical": 0,
            "usage_percent": 0,
            "load_avg": [0, 0, 0],
            "error": "psutil not installed"
        }


def get_gpu_info() -> Dict[str, Any]:
    """获取GPU信息"""
    try:
        import subprocess
        result = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout
        
        if platform.system() == 'Darwin':
            if 'Apple M' in output or 'Apple Silicon' in output:
                mem_info = get_memory_info()
                total_mem = mem_info.get('total_bytes', 0)
                used_mem = mem_info.get('used_bytes', 0)
                return {
                    "type": "unified",
                    "vendor": "Apple",
                    "model": "Apple Silicon (Unified Memory)",
                    "total": 1,
                    "available": 1 if total_mem > 0 else 0,
                    "used": 1 if used_mem > 0 else 0,
                    "memory_shared": True,
                    "total_memory_bytes": total_mem,
                    "used_memory_bytes": used_mem,
                    "utilization_percent": round(used_mem / total_mem * 100, 1) if total_mem > 0 else 0
                }
        
        return {
            "type": "unknown",
            "total": 0,
            "available": 0,
            "used": 0,
            "error": "No GPU detected"
        }
    except Exception:
        return {
            "type": "unknown",
            "total": 0,
            "available": 0,
            "used": 0,
            "error": "Could not detect GPU"
        }


def get_all_metrics() -> Dict[str, Any]:
    """获取所有系统指标"""
    return {
        "system": get_system_info(),
        "memory": get_memory_info(),
        "storage": get_storage_info(),
        "cpu": get_cpu_info(),
        "gpu": get_gpu_info()
    }