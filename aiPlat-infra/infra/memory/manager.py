import uuid
import psutil
import threading
import time
import logging
from typing import Dict, Optional, List, Any
from .base import MemoryManager
from .schemas import MemoryRequest, Allocation, MemoryStats, MemoryLimit, MemoryConfig

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class RAMMemoryManager(MemoryManager):
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._allocations: Dict[str, Allocation] = {}
        self._limits: Dict[str, MemoryLimit] = {}
        self._oom_threshold = config.oom_threshold

    def allocate(self, request: MemoryRequest) -> Allocation:
        allocation = Allocation(
            id=str(uuid.uuid4()),
            address=0,
            size=request.size,
        )
        self._allocations[allocation.id] = allocation
        return allocation

    def release(self, allocation_id: str) -> bool:
        if allocation_id in self._allocations:
            del self._allocations[allocation_id]
            return True
        return False

    def get_stats(self, node_id: str) -> MemoryStats:
        mem = psutil.virtual_memory()
        return MemoryStats(
            total=mem.total,
            used=mem.used,
            available=mem.available,
            cached=mem.cached,
        )

    def set_limit(self, tenant_id: str, limit: MemoryLimit) -> bool:
        self._limits[tenant_id] = limit
        return True

    def enable_oom_protection(self, threshold: float) -> bool:
        self._oom_threshold = threshold
        return True

    def compact(self, node_id: str) -> bool:
        import gc

        gc.collect()
        return True


class VRAMMemoryManager(MemoryManager):
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._allocations: Dict[str, Allocation] = {}
        self._limits: Dict[str, MemoryLimit] = {}
        self._oom_threshold = config.oom_threshold
        self._oom_protection_enabled = False
        self._oom_monitor_thread: Optional[threading.Thread] = None
        self._oom_stop_event = threading.Event()
        self._gpu_handles: Dict[int, Any] = {}
        self._gpu_count = 0
        self._current_gpu_index = config.backend == "multi-gpu" and -1 or 0
        self._base_address = 0x1000000000000
        self._address_counter = 0
        self._lock = threading.Lock()
        self._initialized = False
        self._init_nvml()

    def _init_nvml(self):
        if not PYNVML_AVAILABLE:
            logger.warning("pynvml not available. GPU memory management will be simulated.")
            self._initialized = False
            return
        try:
            pynvml.nvmlInit()
            self._gpu_count = pynvml.nvmlDeviceGetCount()
            for i in range(self._gpu_count):
                self._gpu_handles[i] = pynvml.nvmlDeviceGetHandleByIndex(i)
            self._initialized = True
            logger.info(f"NVML initialized successfully. Found {self._gpu_count} GPU(s).")
        except pynvml.NVMLError as e:
            logger.error(f"Failed to initialize NVML: {e}")
            self._initialized = False

    def _get_gpu_memory_info(self, gpu_index: int = 0) -> Optional[Dict]:
        if not self._initialized:
            return None
        if gpu_index not in self._gpu_handles:
            return None
        try:
            handle = self._gpu_handles[gpu_index]
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "total": mem_info.total,
                "used": mem_info.used,
                "free": mem_info.free,
            }
        except pynvml.NVMLError as e:
            logger.error(f"Failed to get GPU memory info for GPU {gpu_index}: {e}")
            return None

    def _generate_address(self) -> int:
        with self._lock:
            self._address_counter += 1
            return self._base_address + (self._address_counter * 4096)

    def allocate(self, request: MemoryRequest) -> Allocation:
        allocation_id = str(uuid.uuid4())
        gpu_index = self._current_gpu_index
        if gpu_index == -1 and self._gpu_count > 0:
            gpu_index = 0
        mem_info = self._get_gpu_memory_info(gpu_index)
        if mem_info is None:
            logger.warning("Unable to get GPU memory info, allocating with simulated address.")
            address = self._generate_address()
        else:
            if request.size > mem_info["free"]:
                raise MemoryError(
                    f"Requested {request.size} bytes but only {mem_info['free']} bytes available on GPU {gpu_index}"
                )
            address = self._generate_address()
        allocation = Allocation(
            id=allocation_id,
            address=address,
            size=request.size,
        )
        with self._lock:
            self._allocations[allocation_id] = allocation
        logger.debug(f"Allocated {request.size} bytes at address {hex(address)} (ID: {allocation_id})")
        return allocation

    def release(self, allocation_id: str) -> bool:
        with self._lock:
            if allocation_id in self._allocations:
                allocation = self._allocations[allocation_id]
                del self._allocations[allocation_id]
                logger.debug(f"Released allocation {allocation_id} ({allocation.size} bytes)")
                return True
        logger.warning(f"Attempted to release non-existent allocation {allocation_id}")
        return False

    def get_stats(self, node_id: str) -> MemoryStats:
        gpu_index = self._current_gpu_index
        if gpu_index == -1 and self._gpu_count > 0:
            gpu_index = 0
        mem_info = self._get_gpu_memory_info(gpu_index)
        if mem_info is None:
            return MemoryStats(total=0, used=0, available=0, cached=0)
        total_allocated = sum(a.size for a in self._allocations.values())
        return MemoryStats(
            total=mem_info["total"],
            used=mem_info["used"],
            available=mem_info["free"],
            cached=total_allocated,
        )

    def set_limit(self, tenant_id: str, limit: MemoryLimit) -> bool:
        with self._lock:
            self._limits[tenant_id] = limit
        logger.debug(f"Set memory limit for tenant {tenant_id}: soft={limit.soft_limit}, hard={limit.hard_limit}")
        return True

    def enable_oom_protection(self, threshold: float) -> bool:
        if not self._initialized:
            logger.warning("Cannot enable OOM protection: NVML not initialized")
            return False
        self._oom_threshold = threshold
        self._oom_protection_enabled = True
        self._oom_stop_event.clear()
        if self._oom_monitor_thread is None or not self._oom_monitor_thread.is_alive():
            self._oom_monitor_thread = threading.Thread(target=self._oom_monitor_loop, daemon=True)
            self._oom_monitor_thread.start()
        logger.info(f"OOM protection enabled with threshold {threshold}")
        return True

    def disable_oom_protection(self) -> bool:
        self._oom_protection_enabled = False
        self._oom_stop_event.set()
        if self._oom_monitor_thread:
            self._oom_monitor_thread.join(timeout=2.0)
        self._oom_monitor_thread = None
        logger.info("OOM protection disabled")
        return True

    def _oom_monitor_loop(self):
        while not self._oom_stop_event.is_set():
            try:
                gpu_index = self._current_gpu_index
                if gpu_index == -1 and self._gpu_count > 0:
                    gpu_index = 0
                mem_info = self._get_gpu_memory_info(gpu_index)
                if mem_info:
                    used_ratio = mem_info["used"] / mem_info["total"]
                    if used_ratio >= self._oom_threshold:
                        logger.warning(
                            f"GPU memory usage ({used_ratio:.2%}) exceeds threshold ({self._oom_threshold:.2%})"
                        )
            except Exception as e:
                logger.error(f"Error in OOM monitor loop: {e}")
            self._oom_stop_event.wait(timeout=1.0)

    def compact(self, node_id: str) -> bool:
        import gc

        with self._lock:
            gc.collect()
        logger.debug(f"Memory compact completed for node {node_id}")
        return True

    def get_all_gpu_stats(self) -> List[MemoryStats]:
        if not self._initialized:
            return []
        stats_list = []
        for i in range(self._gpu_count):
            mem_info = self._get_gpu_memory_info(i)
            if mem_info:
                stats_list.append(
                    MemoryStats(
                        total=mem_info["total"],
                        used=mem_info["used"],
                        available=mem_info["free"],
                        cached=0,
                    )
                )
        return stats_list

    def set_active_gpu(self, gpu_index: int) -> bool:
        if gpu_index < 0 or gpu_index >= self._gpu_count:
            logger.error(f"Invalid GPU index: {gpu_index}")
            return False
        self._current_gpu_index = gpu_index
        logger.info(f"Active GPU set to {gpu_index}")
        return True

    def get_gpu_count(self) -> int:
        return self._gpu_count

    def get_allocator_name(self, gpu_index: int = 0) -> Optional[str]:
        if not self._initialized:
            return None
        try:
            handle = self._gpu_handles.get(gpu_index)
            if not handle:
                return None
            name = pynvml.nvmlDeviceGetName(handle)
            return name.decode('utf-8') if isinstance(name, bytes) else name
        except pynvml.NVMLError:
            return None

    def __del__(self):
        if hasattr(self, "_oom_stop_event"):
            self._oom_stop_event.set()
        if hasattr(self, "_oom_monitor_thread") and self._oom_monitor_thread:
            self._oom_monitor_thread.join(timeout=1.0)
        if self._initialized and PYNVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
