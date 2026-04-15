from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import asyncio
from pathlib import Path


class ProdEnvironment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class StorageBackend(Enum):
    MEMORY = "memory"
    FILE = "file"
    DATABASE = "database"
    S3 = "s3"


class FeedbackStorageType(Enum):
    SESSION = "session"
    LONG_TERM = "long_term"
    PERSISTENT = "persistent"


@dataclass
class ProdFeedbackConfig:
    environment: ProdEnvironment = ProdEnvironment.DEVELOPMENT
    storage_backend: StorageBackend = StorageBackend.MEMORY
    storage_path: Optional[str] = None
    max_retention_days: int = 30
    enable_compression: bool = False
    enable_encryption: bool = False


@dataclass
class StoredFeedback:
    id: str
    session_id: str
    feedback_type: str
    content: Any
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    environment: ProdEnvironment = ProdEnvironment.DEVELOPMENT
    storage_type: FeedbackStorageType = FeedbackStorageType.SESSION


class ProdFeedbackStore:
    def __init__(self, config: ProdFeedbackConfig):
        self.config = config
        self._memory_store: List[StoredFeedback] = []
        self._session_index: Dict[str, List[str]] = {}

    async def store(
        self,
        session_id: str,
        feedback_type: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        storage_type: FeedbackStorageType = FeedbackStorageType.SESSION,
    ) -> StoredFeedback:
        feedback = StoredFeedback(
            id=f"fb_{datetime.now().timestamp()}",
            session_id=session_id,
            feedback_type=feedback_type,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
            environment=self.config.environment,
            storage_type=storage_type,
        )

        if self.config.storage_backend == StorageBackend.MEMORY:
            self._memory_store.append(feedback)
            if session_id not in self._session_index:
                self._session_index[session_id] = []
            self._session_index[session_id].append(feedback.id)
        elif self.config.storage_backend == StorageBackend.FILE:
            await self._store_to_file(feedback)
        elif self.config.storage_backend == StorageBackend.DATABASE:
            await self._store_to_db(feedback)

        return feedback

    async def retrieve(
        self,
        session_id: Optional[str] = None,
        feedback_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[StoredFeedback]:
        if self.config.storage_backend == StorageBackend.MEMORY:
            result = self._memory_store
            if session_id:
                result = [f for f in result if f.session_id == session_id]
            if feedback_type:
                result = [f for f in result if f.feedback_type == feedback_type]
            return result[-limit:]
        return []

    async def delete(self, feedback_id: str) -> bool:
        if self.config.storage_backend == StorageBackend.MEMORY:
            for i, f in enumerate(self._memory_store):
                if f.id == feedback_id:
                    self._memory_store.pop(i)
                    return True
        return False

    async def cleanup(self, older_than_days: Optional[int] = None):
        if not older_than_days:
            older_than_days = self.config.max_retention_days
        cutoff = datetime.now().timestamp() - (older_than_days * 86400)
        self._memory_store = [
            f for f in self._memory_store
            if f.timestamp.timestamp() > cutoff
        ]

    async def _store_to_file(self, feedback: StoredFeedback):
        if not self.config.storage_path:
            return
        path = Path(self.config.storage_path)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{feedback.id}.json"
        with open(file_path, "w") as f:
            json.dump({
                "id": feedback.id,
                "session_id": feedback.session_id,
                "feedback_type": feedback.feedback_type,
                "content": feedback.content,
                "timestamp": feedback.timestamp.isoformat(),
                "metadata": feedback.metadata,
            }, f)

    async def _store_to_db(self, feedback: StoredFeedback):
        pass


class ProdFeedbackAnalytics:
    def __init__(self, store: ProdFeedbackStore):
        self.store = store

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        feedbacks = await self.store.retrieve(session_id=session_id, limit=1000)
        if not feedbacks:
            return {"session_id": session_id, "total": 0}

        by_type: Dict[str, int] = {}
        for f in feedbacks:
            by_type[f.feedback_type] = by_type.get(f.feedback_type, 0) + 1

        return {
            "session_id": session_id,
            "total": len(feedbacks),
            "by_type": by_type,
            "first_feedback": feedbacks[0].timestamp.isoformat() if feedbacks else None,
            "last_feedback": feedbacks[-1].timestamp.isoformat() if feedbacks else None,
        }

    async def get_error_rate(self, session_id: str) -> float:
        feedbacks = await self.store.retrieve(session_id=session_id, limit=1000)
        if not feedbacks:
            return 0.0
        errors = [f for f in feedbacks if f.feedback_type == "error"]
        return len(errors) / len(feedbacks)


class ProductionFeedbackLoop:
    def __init__(self, config: Optional[ProdFeedbackConfig] = None):
        self.config = config or ProdFeedbackConfig()
        self.store = ProdFeedbackStore(self.config)
        self.analytics = ProdFeedbackAnalytics(self.store)
        self._enabled = True

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    async def record(
        self,
        session_id: str,
        feedback_type: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
        storage_type: FeedbackStorageType = FeedbackStorageType.SESSION,
    ):
        if not self._enabled:
            return None
        return await self.store.store(session_id, feedback_type, content, metadata, storage_type)

    async def retrieve(
        self,
        session_id: Optional[str] = None,
        feedback_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[StoredFeedback]:
        return await self.store.retrieve(session_id, feedback_type, limit)

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        return await self.analytics.get_session_summary(session_id)

    async def get_error_rate(self, session_id: str) -> float:
        return await self.analytics.get_error_rate(session_id)

    async def cleanup(self):
        await self.store.cleanup()


def create_production_feedback(config: Optional[ProdFeedbackConfig] = None) -> ProductionFeedbackLoop:
    return ProductionFeedbackLoop(config)


_production_feedback = ProductionFeedbackLoop()


def get_production_feedback() -> ProductionFeedbackLoop:
    return _production_feedback