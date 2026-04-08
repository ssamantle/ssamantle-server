from pydantic import BaseModel


class ItemBase(BaseModel):
    """아이템 기본 모델"""
    name: str
    description: str | None = None


class ItemCreate(ItemBase):
    """아이템 생성 요청 모델"""
    pass


class Item(ItemBase):
    """아이템 응답 모델"""
    id: int

    class Config:
        from_attributes = True
