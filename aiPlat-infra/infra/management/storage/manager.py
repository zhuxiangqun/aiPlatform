"""
Storage Manager

Manages storage management including PVCs, vector collections, and models.
In standalone mode, monitors real disk usage and directory sizes.
"""

from typing import Dict, Any, List, Optional
from ..base import ManagementBase, Status, HealthStatus, Metrics, DiagnosisResult
from ..schemas import ResourceStats
from datetime import datetime
import time
import os


def get_real_storage_info() -> Dict[str, Any]:
    """Get real storage information for standalone mode."""
    result = {
        "disk": {},
        "directories": [],
        "collections": []
    }
    
    try:
        import shutil
        
        total, used, free = shutil.disk_usage("/")
        result["disk"] = {
            "total_gb": round(total / 1024 / 1024 / 1024, 1),
            "used_gb": round(used / 1024 / 1024 / 1024, 1),
            "free_gb": round(free / 1024 / 1024 / 1024, 1),
            "usage_percent": round(used / total * 100, 1)
        }
        
        dirs_to_check = [
            {"path": "/Users/apple/workdata/person/zy/aiPlatform", "name": "aiPlatform"},
            {"path": "/tmp", "name": "tmp"},
        ]
        
        for dir_info in dirs_to_check:
            path = dir_info["path"]
            if os.path.exists(path):
                try:
                    import subprocess
                    result_subprocess = subprocess.run(
                        ['du', '-sm', '--max-depth=0', path],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    if result_subprocess.returncode == 0:
                        size_str = result_subprocess.stdout.split()[0]
                        size_mb = float(size_str)
                    else:
                        size_mb = 0
                    
                    result["directories"].append({
                        "name": dir_info["name"],
                        "path": path,
                        "size_mb": size_mb,
                        "exists": True
                    })
                except Exception:
                    result["directories"].append({
                        "name": dir_info["name"],
                        "path": path,
                        "size_mb": 0,
                        "exists": True
                    })
    except Exception as e:
        result["error"] = str(e)
    
    return result


class PVCInfo:
    def __init__(self, name: str, namespace: str, capacity: str, storage_class: str, access_mode: str, status: str, created_at: datetime):
        self.name = name
        self.namespace = namespace
        self.capacity = capacity
        self.storage_class = storage_class
        self.access_mode = access_mode
        self.status = status
        self.created_at = created_at


class VectorCollectionInfo:
    def __init__(self, name: str, dimension: int, index_type: str, metric: str, count: int, status: str, created_at: datetime = None):
        self.name = name
        self.dimension = dimension
        self.index_type = index_type
        self.metric = metric
        self.count = count
        self.status = status
        self.created_at = created_at or datetime.now()


class StorageManager(ManagementBase):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._pvcs: Dict[str, PVCInfo] = {}
        self._collections: Dict[str, VectorCollectionInfo] = {}
        self._standalone_mode = config.get("standalone_mode", True) if config else True
        self._last_refresh: float = 0
        self._cache_ttl: float = 30.0
    
    def _refresh_storage_info(self):
        """Refresh storage information from real system (with cache)."""
        if not self._standalone_mode:
            return
        
        now = time.time()
        if self._last_refresh and (now - self._last_refresh) < self._cache_ttl:
            return
        
        storage_info = get_real_storage_info()
        
        # Convert disk info to PVC-like format
        disk = storage_info.get("disk", {})
        if disk:
            self._pvcs = {
                "root": PVCInfo(
                    name="root-disk",
                    namespace="system",
                    capacity=f"{disk.get('total_gb', 0)}Gi",
                    storage_class="local",
                    access_mode="ReadWriteOnce",
                    status="Bound" if disk.get('usage_percent', 0) < 90 else "Warning",
                    created_at=datetime.now()
                )
            }
        
        # Convert directories to collections-like format
        self._collections = {}
        for i, dir_info in enumerate(storage_info.get("directories", [])):
            if dir_info.get("exists"):
                col_name = dir_info["name"]
                self._collections[col_name] = VectorCollectionInfo(
                    name=col_name,
                    dimension=0,
                    index_type="local",
                    metric="N/A",
                    count=0,
status="Active"
                 )
        self._last_refresh = time.time()
    
    def _needs_refresh(self) -> bool:
        return not self._last_refresh or (time.time() - self._last_refresh) >= self._cache_ttl

    async def get_status(self) -> Status:
        """Get storage module status."""
        try:
            if self._standalone_mode:
                self._refresh_storage_info()
            
            if not self._pvcs and not self._collections:
                return Status.UNKNOWN
            
            failed_pvcs = sum(1 for pvc in self._pvcs.values() if pvc.status == "Failed")
            failed_collections = sum(1 for col in self._collections.values() if col.status == "Error")
            
            total = len(self._pvcs) + len(self._collections)
            failed = failed_pvcs + failed_collections
            
            if failed == 0:
                return Status.HEALTHY
            elif failed < total:
                return Status.DEGRADED
            else:
                return Status.UNHEALTHY
        except Exception:
            return Status.UNKNOWN
    
    async def get_metrics(self) -> List[Metrics]:
        """Get storage metrics."""
        if self._standalone_mode:
            self._refresh_storage_info()
        
        metrics = []
        timestamp = time.time()
        
        metrics.append(Metrics(
            name="storage.pvc_count",
            value=len(self._pvcs),
            unit="count",
            timestamp=timestamp,
            labels={"module": "storage"}
        ))
        
        metrics.append(Metrics(
            name="storage.collection_count",
            value=len(self._collections),
            unit="count",
            timestamp=timestamp,
            labels={"module": "storage"}
        ))
        
        for name, pvc in self._pvcs.items():
            capacity = float(pvc.capacity.replace("Gi", "")) if "Gi" in pvc.capacity else 0
            metrics.append(Metrics(
                name="storage.pvc_capacity",
                value=capacity,
                unit="GiB",
                timestamp=timestamp,
                labels={"pvc": name, "namespace": pvc.namespace, "module": "storage"}
            ))
        
        return metrics
    
    async def health_check(self) -> HealthStatus:
        """Perform storage health check."""
        if self._standalone_mode:
            self._refresh_storage_info()
        
        status = await self.get_status()
        issues = []
        
        for name, pvc in self._pvcs.items():
            if pvc.status in ["Failed", "Lost"]:
                issues.append(f"PVC {name} in namespace {pvc.namespace} is {pvc.status}")
        
        for name, col in self._collections.items():
            if col.status == "Error":
                issues.append(f"Vector collection {name} is in error state")
        
        details = {"pvcs": len(self._pvcs), "collections": len(self._collections)}
        
        if status == Status.HEALTHY:
            return HealthStatus(
                status=status,
                message="Storage is healthy",
                details=details
            )
        else:
            return HealthStatus(
                status=status,
                message=f"{len(issues)} storage issues detected",
                details={**details, "issues": issues}
            )
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config
    
    async def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config.update(config)
    
    async def diagnose(self) -> DiagnosisResult:
        """Run diagnostic checks for storage."""
        if self._standalone_mode:
            self._refresh_storage_info()
        issues = []
        recommendations = []
        details = {}
        
        try:
            status = await self.get_status()
            details["status"] = status.value
            
            if status == Status.UNHEALTHY:
                issues.append("Storage module is unhealthy")
                recommendations.append("Check disk space and permissions")
            
            healthy = len(issues) == 0
            return DiagnosisResult(
                healthy=healthy,
                issues=issues,
                recommendations=recommendations,
                details=details
            )
        except Exception as e:
            return DiagnosisResult(
                healthy=False,
                issues=[f"Diagnosis failed: {str(e)}"],
                recommendations=["Check storage configuration"],
                details={"error": str(e)}
            )
    
    async def list_pvcs(self) -> List[Dict[str, Any]]:
        """List all PVCs."""
        if self._standalone_mode:
            self._refresh_storage_info()
            # Return real disk info as PVC
            storage_info = get_real_storage_info()
            disk = storage_info.get("disk", {})
            if disk:
                return [{
                    "name": "root-disk",
                    "namespace": "system",
                    "capacity": disk.get("total_gb", 0),
                    "used": disk.get("used_gb", 0),
                    "available": disk.get("free_gb", 0),
                    "usagePercent": disk.get("usage_percent", 0),
                    "storageClass": "local",
                    "status": "Bound" if disk.get("usage_percent", 0) < 90 else "Warning",
                    "createdAt": datetime.now().isoformat()
                }]
        return [
            {
                "name": pvc.name,
                "namespace": pvc.namespace,
                "capacity": pvc.capacity,
                "storage_class": pvc.storage_class,
                "access_mode": pvc.access_mode,
                "status": pvc.status,
                "created_at": pvc.created_at.isoformat() if pvc.created_at else None
            }
            for pvc in self._pvcs.values()
        ]
    
    async def get_pvc(self, name: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """Get PVC details."""
        if self._standalone_mode:
            pvcs = await self.list_pvcs()
            for pvc in pvcs:
                if pvc["name"] == name:
                    return pvc
            return None
        
        key = f"{namespace}/{name}"
        pvc = self._pvcs.get(key)
        if pvc:
            return {
                "name": pvc.name,
                "namespace": pvc.namespace,
                "capacity": pvc.capacity,
                "storage_class": pvc.storage_class,
                "access_mode": pvc.access_mode,
                "status": pvc.status,
                "created_at": pvc.created_at.isoformat() if pvc.created_at else None
            }
        return None
    
    async def create_pvc(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a PVC."""
        if self._standalone_mode:
            raise RuntimeError("Create PVC not supported in standalone mode")
        
        name = config.get("name", f"pvc-{len(self._pvcs) + 1}")
        namespace = config.get("namespace", "default")
        key = f"{namespace}/{name}"
        
        pvc = PVCInfo(
            name=name,
            namespace=namespace,
            capacity=config.get("capacity", "100Gi"),
            storage_class=config.get("storage_class", "standard"),
            access_mode=config.get("access_mode", "ReadWriteOnce"),
            status="Pending",
            created_at=datetime.now()
        )
        
        self._pvcs[key] = pvc
        return {"name": name, "namespace": namespace, "status": "created"}
    
    async def delete_pvc(self, name: str, namespace: str = "default") -> bool:
        """Delete a PVC."""
        if self._standalone_mode:
            raise RuntimeError("Delete PVC not supported in standalone mode")
        
        key = f"{namespace}/{name}"
        if key in self._pvcs:
            del self._pvcs[key]
            return True
        return False
    
    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all vector collections."""
        if self._standalone_mode:
            self._refresh_storage_info()
            storage_info = get_real_storage_info()
            
            # Return directories as collections
            collections = []
            for i, dir_info in enumerate(storage_info.get("directories", [])):
                if dir_info.get("exists"):
                    collections.append({
                        "id": f"col-{i}",
                        "name": dir_info["name"],
                        "vectors": 0,
                        "dimension": 0,
                        "size": f"{dir_info['size_mb']} MB",
                        "status": "green",
                        "createdAt": datetime.now().isoformat()
                    })
            return collections
        
        return [
            {
                "id": f"col-{name}",
                "name": col.name,
                "vectors": col.count,
                "dimension": col.dimension,
                "size": f"{col.count * col.dimension * 4 / 1024 / 1024:.2f} MB",
                "status": col.status.lower() if col.status else "green",
                "createdAt": col.created_at.isoformat() if hasattr(col, 'created_at') and col.created_at else None
            }
            for name, col in self._collections.items()
        ]
    
    async def get_collection(self, name: str) -> Optional[Dict[str, Any]]:
        """Get collection details."""
        collections = await self.list_collections()
        for col in collections:
            if col["name"] == name:
                return col
        return None
    
    async def create_collection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a vector collection."""
        if self._standalone_mode:
            raise RuntimeError("Create collection not supported in standalone mode")
        
        name = config.get("name", f"collection-{len(self._collections) + 1}")
        
        col = VectorCollectionInfo(
            name=name,
            dimension=config.get("dimension", 1536),
            index_type=config.get("index_type", "IVF_FLAT"),
            metric=config.get("metric", "L2"),
            count=0,
            status="Created"
        )
        
        self._collections[name] = col
        return {"name": name, "status": "created"}
    
    async def delete_collection(self, name: str) -> bool:
        """Delete a vector collection."""
        if self._standalone_mode:
            raise RuntimeError("Delete collection not supported in standalone mode")
        
        if name in self._collections:
            del self._collections[name]
            return True
        return False
    
    async def resize_pvc(self, name: str, size: str, namespace: str = "default") -> Dict[str, Any]:
        """Resize a PVC."""
        if self._standalone_mode:
            return {"name": name, "size": size, "status": "resizing"}
        
        if name in self._pvcs:
            self._pvcs[name]["size"] = size
            return {"name": name, "size": size, "status": "resizing"}
        return {"name": name, "status": "not_found"}
    
    async def create_snapshot(self, pvc_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Create a PVC snapshot."""
        import uuid
        snapshot_name = f"snapshot-{pvc_name}-{uuid.uuid4().hex[:8]}"
        
        return {
            "name": snapshot_name,
            "pvc": pvc_name,
            "status": "created",
            "created_at": datetime.now().isoformat()
        }
    
    async def get_vector_status(self) -> Dict[str, Any]:
        """Get vector database status."""
        if self._standalone_mode:
            return {
                "status": "standalone",
                "collections": len(self._collections),
                "type": "milvus"
            }
        
        return {
            "status": "running",
            "collections": len(self._collections),
            "type": "milvus"
        }
    
    async def list_model_storage(self) -> List[Dict[str, Any]]:
        """List model storage."""
        return []