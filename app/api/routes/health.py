from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """헬스 체크"""
    return {"status": "healthy"}

