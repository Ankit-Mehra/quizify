from pydantic import BaseModel
from datetime import datetime
class User(BaseModel):
    email: str
    password: str

