from fastapi import APIRouter

router = APIRouter(
    prefix="/api/items",
    tags=["items"],
)


@router.get("/")
async def get_items():
    """모든 아이템 조회"""
    return {
        "items": [
            {"id": 1, "name": "Item 1", "description": "First item"},
            {"id": 2, "name": "Item 2", "description": "Second item"},
        ]
    }


@router.get("/{item_id}")
async def get_item(item_id: int):
    """특정 아이템 조회"""
    return {"id": item_id, "name": f"Item {item_id}", "description": "Example item"}


@router.post("/")
async def create_item(name: str, description: str | None = None):
    """새 아이템 생성"""
    return {"id": 3, "name": name, "description": description}
