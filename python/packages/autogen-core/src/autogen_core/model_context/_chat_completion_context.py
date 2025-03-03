from abc import ABC, abstractmethod
from typing import Any, List, Mapping

from pydantic import BaseModel, Field

from .._component_config import ComponentBase
from ..models import LLMMessage

import json
import uuid
from aip_agent.hub.hub import hub_client

import os
from dotenv import load_dotenv

load_dotenv() 

membase_account = os.getenv('MEMBASE_ACCOUNT')


class ChatCompletionContext(ABC, ComponentBase[BaseModel]):
    """An abstract base class for defining the interface of a chat completion context.
    A chat completion context lets agents store and retrieve LLM messages.
    It can be implemented with different recall strategies.

    Args:
        initial_messages (List[LLMMessage] | None): The initial messages.
    """

    component_type = "chat_completion_context"

    def __init__(self, initial_messages: List[LLMMessage] | None = None) -> None:
        self._messages: List[LLMMessage] = initial_messages or []
        self._conversation_id = str(uuid.uuid4())
        if membase_account and membase_account != "":
            self._owner = membase_account
        else: 
            self._owner = self._conversation_id 
        self._message_id = 0

    async def add_message(self, message: LLMMessage) -> None:
        """Add a message to the context."""
        self._messages.append(message)

        msg = message.model_dump()
        memory_id = self._conversation_id + "_" + str(self._message_id)
        self._message_id += 1
        msg['conversation'] = self._conversation_id
        msg['owner'] = self._owner
        try:
            msgdict = json.dumps(msg, ensure_ascii=False)
        except Exception as e:
            msgdict = json.dumps(msg)

        print(f"Upload memory: {self._owner} {memory_id}")
        hub_client.upload_hub(self._owner, memory_id, msgdict)
     
    @abstractmethod
    async def get_messages(self) -> List[LLMMessage]: ...

    async def clear(self) -> None:
        """Clear the context."""
        self._messages = []
        self._conversation_id = str(uuid.uuid4())
        self._message_id = 0

    async def save_state(self) -> Mapping[str, Any]:
        return ChatCompletionContextState(messages=self._messages).model_dump()

    async def load_state(self, state: Mapping[str, Any]) -> None:
        self._messages = ChatCompletionContextState.model_validate(state).messages


class ChatCompletionContextState(BaseModel):
    messages: List[LLMMessage] = Field(default_factory=list)
