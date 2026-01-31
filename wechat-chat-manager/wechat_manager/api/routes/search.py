"""
Search routes for the WeChat Chat Manager API.

Provides endpoints for:
- Search extracted messages by keyword
- Search with context (surrounding messages)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.search import SearchService
from wechat_manager.api.routes.dependencies import get_storage


router = APIRouter()


class MessageResponse(BaseModel):
    """Response model for a message"""

    id: Optional[int] = None
    contact_id: str
    content: str
    create_time: int
    is_sender: bool
    msg_type: int = 1


class SearchResultItem(BaseModel):
    """Response model for search result with context"""

    match: MessageResponse
    before: List[MessageResponse]
    after: List[MessageResponse]


class SearchResponse(BaseModel):
    """Response model for search"""

    results: List[MessageResponse]
    count: int
    query: str


class SearchWithContextResponse(BaseModel):
    """Response model for search with context"""

    results: List[SearchResultItem]
    count: int
    query: str


def get_search_service(
    storage: EncryptedStorage = Depends(get_storage),
) -> SearchService:
    """Get SearchService instance"""
    return SearchService(storage)


@router.get("/", response_model=SearchResponse)
async def search_messages(
    q: str,
    contact_id: Optional[str] = None,
    limit: int = 100,
    search_service: SearchService = Depends(get_search_service),
):
    """Search extracted messages by keyword"""
    if not q:
        raise HTTPException(status_code=400, detail="Search query is required")

    results = search_service.search(q, contact_id=contact_id, limit=limit)

    return {
        "results": [
            {
                "id": m.id,
                "contact_id": m.contact_id,
                "content": m.content,
                "create_time": m.create_time,
                "is_sender": m.is_sender,
                "msg_type": m.msg_type,
            }
            for m in results
        ],
        "count": len(results),
        "query": q,
    }


@router.get("/with-context", response_model=SearchWithContextResponse)
async def search_with_context(
    q: str,
    contact_id: Optional[str] = None,
    context_lines: int = 2,
    search_service: SearchService = Depends(get_search_service),
):
    """Search messages and return with surrounding context"""
    if not q:
        raise HTTPException(status_code=400, detail="Search query is required")

    results = search_service.search_with_context(
        q, context_lines=context_lines, contact_id=contact_id
    )

    def msg_to_dict(m):
        return {
            "id": m.id,
            "contact_id": m.contact_id,
            "content": m.content,
            "create_time": m.create_time,
            "is_sender": m.is_sender,
            "msg_type": m.msg_type,
        }

    return {
        "results": [
            {
                "match": msg_to_dict(r["match"]),
                "before": [msg_to_dict(m) for m in r["before"]],
                "after": [msg_to_dict(m) for m in r["after"]],
            }
            for r in results
        ],
        "count": len(results),
        "query": q,
    }
