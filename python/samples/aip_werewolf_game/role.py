# role agent for wolf, village, seer, witch

import argparse
import asyncio
import time
import yaml
import logging
from typing import Any, Dict, List

from autogen_core import (
    AgentId,
    MessageContext,
    RoutedAgent,
    try_get_known_serializers_for_type,
    message_handler,
)
from autogen_core.model_context import UnboundedChatCompletionContext, ChatCompletionContext
from autogen_core.models import (
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
    UserMessage,
    AssistantMessage,
)
from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from common import TextMessage
from prompt import get_game_prompt, get_response_format

class PlayerAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        instructions: str,
        model_client: ChatCompletionClient,
        model_context: ChatCompletionContext,
        role_type: str,
    ) -> None:
        super().__init__(description=description)
        self._system_messages: List[LLMMessage] = [SystemMessage(content=instructions)]
        self._model_client = model_client
        self._model_context = model_context
        self._notice_messages: List[LLMMessage] = []
        self._important_info: LLMMessage = None
        self.role_type = role_type
        print(f"=== start agent: {self.id}, role: {self.role_type}")

    @message_handler
    async def handle_message(self, message: TextMessage, ctx: MessageContext) -> TextMessage:
        """Handle incoming messages based on their type."""
    
        user_message = UserMessage(content=message.content, source=message.source)
        await self._model_context.add_message(user_message)

        # For notice messages, only add to context without processing
        if message.type == "system_notice":
            self._notice_messages.append(user_message)
            # Process response
            if "Game over" in message.content:
                print(message.content)
            return TextMessage(type="response", content="", source=self.id.type)
        
        if message.type == "important_info":
            self._important_info = user_message
            return TextMessage(type="response", content="", source=self.id.type)

        # self._notice_messages: List[LLMMessage] = []
        # Get role-specific game prompt and response format
        game_prompt = get_game_prompt(self._id.type, self.role_type)
        response_format = get_response_format(message.type)
        
        # Combine prompts with the current message
        if self._important_info:
            system_prompt = f"{game_prompt}\n\n{self._important_info.content}\n\n{response_format}"
        else:
            system_prompt = f"{game_prompt}\n\n{response_format}"
            
        self._system_messages = [SystemMessage(content=system_prompt)]
        
        # Get LLM response
        input_messages = self._system_messages + self._notice_messages + [user_message]
        response = await self._model_client.create(input_messages)

        # Add response to context and return
        await self._model_context.add_message(AssistantMessage(content=response.content, source="assistant"))
        return TextMessage(type="response", content=response.content, source=self.id.type)

from membase.chain.chain import membase_chain, membase_id
import os
membase_task_id = os.getenv('MEMBASE_TASK_ID')
if not membase_task_id or membase_task_id == "":
    print("'MEMBASE_TASK_ID' is not set, user defined")
    raise Exception("'MEMBASE_TASK_ID' is not set, user defined")

async def main(moderator_id: str, model_config: Dict[str, Any]) -> None:

    membase_chain.register(membase_id)
    print(f"{membase_id} is register onchain")
    time.sleep(3)

    membase_chain.joinTask(membase_task_id, membase_id)
    print(f"{membase_id} join task {membase_task_id} onchain")
    time.sleep(3)
    
    # start the game
    runtime = GrpcWorkerAgentRuntime('localhost:50060')
    runtime.add_message_serializer(try_get_known_serializers_for_type(TextMessage))
    await runtime.start()

    role_msg = await runtime.send_message(
        TextMessage(type="register",content="join werewolf game", source=membase_id),
        AgentId(moderator_id, membase_task_id),
        sender=AgentId(membase_id, membase_task_id)
    )

    model_client = ChatCompletionClient.load_component(model_config)
    ins = ""
    agentid = membase_id
    role_type = role_msg.content
    await PlayerAgent.register(
        runtime,
        agentid,
        lambda: PlayerAgent(
            description=f"You are player in werewolf game",
            instructions=ins,
            model_client=model_client,
            model_context=UnboundedChatCompletionContext(),
            role_type=role_type,
        ),
    )

    await runtime.stop_when_signal()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a chess game between two agents.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument(
        "--model-config", type=str, help="Path to the model configuration file.", default="model_config.yml"
    )
    parser.add_argument(
        "--moderator", type=str, help="moderator id", default="board_starter"
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("autogen_core").setLevel(logging.DEBUG)
        file_name = "werewolf_game_" + membase_id + ".log"
        handler = logging.FileHandler(file_name)
        logging.getLogger("autogen_core").addHandler(handler)

    with open(args.model_config, "r") as f:
        model_config = yaml.safe_load(f)

    asyncio.run(main(args.moderator, model_config))