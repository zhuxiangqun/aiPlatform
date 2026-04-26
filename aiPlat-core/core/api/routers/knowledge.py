from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import CollectionCreateRequest, DocumentCreateRequest, SearchRequest

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _km(rt: RuntimeDep):
    return getattr(rt, "knowledge_manager", None) if rt else None


# ==================== Knowledge Management ====================


@router.get("/knowledge/collections")
async def list_collections(limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List knowledge collections"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collections = await km.list_collections(limit=limit, offset=offset)
    counts = km.get_collection_count()
    return {
        "collections": [
            {
                "collection_id": c.id,
                "name": c.name,
                "description": c.description,
                "status": c.status,
                "document_count": c.document_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in collections
        ],
        "total": counts["total"],
    }


@router.post("/knowledge/collections")
async def create_collection(request: CollectionCreateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create knowledge collection"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collection = await km.create_collection(name=request.name, description=request.description, metadata=request.metadata)
    return {"collection_id": collection.id, "status": "created"}


@router.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get collection details"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collection = await km.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    return {
        "collection_id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "status": collection.status,
        "config": collection.config,
        "document_count": collection.document_count,
        "total_size_mb": collection.total_size_mb,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
        "metadata": collection.metadata,
    }


@router.put("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Update collection"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collection = await km.update_collection(collection_id, name=request.get("name"), description=request.get("description"), config=request.get("config"))
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    return {"status": "updated", "collection_id": collection_id}


@router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete collection"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    success = await km.delete_collection(collection_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    return {"status": "deleted", "collection_id": collection_id}


@router.post("/knowledge/collections/{collection_id}/reindex")
async def reindex_collection(collection_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Reindex collection"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    success = await km.reindex_collection(collection_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    docs = await km.list_documents(collection_id)
    return {"status": "reindexed", "documents_reindexed": len(docs)}


@router.post("/knowledge/documents")
async def create_document(request: DocumentCreateRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create document"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collection_id = request.metadata.get("collection_id") if request.metadata else None
    if collection_id:
        collection = await km.get_collection(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    doc = await km.upload_document(
        collection_id=collection_id or "default",
        name=request.metadata.get("name", "untitled") if request.metadata else "untitled",
        doc_type=request.metadata.get("type", "txt") if request.metadata else "txt",
        content=b"",
        metadata=request.metadata,
    )
    return {"document_id": doc.id, "status": "created"}


@router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get document"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    doc = await km.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return {
        "document_id": doc.id,
        "collection_id": doc.collection_id,
        "name": doc.name,
        "type": doc.type,
        "size_mb": doc.size_mb,
        "status": doc.status,
        "chunks": doc.chunks,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("/knowledge/collections/{collection_id}/documents")
async def list_documents(collection_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List documents"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    collection = await km.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    docs = await km.list_documents(collection_id, limit=limit, offset=offset)
    return {
        "documents": [{"document_id": d.id, "name": d.name, "type": d.type, "status": d.status, "chunks": d.chunks} for d in docs],
        "total": collection.document_count,
    }


@router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete document"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    success = await km.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return {"status": "deleted", "document_id": document_id}


@router.post("/knowledge/search")
async def search_knowledge(request: SearchRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Search knowledge"""
    km = _km(rt)
    if not km:
        raise HTTPException(status_code=503, detail="KnowledgeManager not initialized")
    results = await km.search(collection_id=request.metadata.get("collection_id") if request.metadata else "", query=request.query, top_k=request.limit)
    return {"results": [{"content": r.content, "score": r.score, "metadata": r.metadata} for r in results], "total": len(results)}


@router.get("/knowledge/collections/{collection_id}/search/logs")
async def get_search_logs(collection_id: str, limit: int = 100, offset: int = 0):
    """Get search logs"""
    return {"logs": [], "total": 0}

