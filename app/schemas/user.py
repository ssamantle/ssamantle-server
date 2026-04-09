from pydantic import BaseModel


class NicknameCheckResponse(BaseModel):
    isDuplicate: bool
