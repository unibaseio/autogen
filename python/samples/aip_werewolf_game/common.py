from pydantic import BaseModel # type: ignore

class TextMessage(BaseModel):
    # System message types
    # register - Player registration
    # system_notice - System notifications
    # response - Player responses
    # important_info - Important information
    
    # Night phase actions
    # night_kill - Werewolf kill vote
    # divine - Seer's investigation
    # save - Witch's healing potion
    # poison - Witch's poison potion
    
    # Day phase actions
    # day_discuss - Daytime discussion
    # day_vote - Daytime voting
    
    type: str  # Message type
    source: str  # Message source
    content: str  # Message content

class Player(BaseModel):
    name: str  # Player name
    type: str  # Player role type: "wolf", "villager", "witch", "seer"
    state: str  # Player state: "alive" or "dead"

