from pydantic import BaseModel # type: ignore

class TextMessage(BaseModel):    
    type: str  # Message type
    source: str  # Message source
    content: str  # Message content

class Player(BaseModel):
    name: str  # Player name
    type: str  # Player role type: "wolf", "villager", "witch", "seer"
    state: str  # Player state: "alive" or "dead"