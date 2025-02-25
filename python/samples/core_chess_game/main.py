"""This is an example of simulating a chess game with two agents
that play against each other, using tools to reason about the game state
and make moves. The agents subscribe to the default topic and publish their
moves to the default topic."""

import argparse
import asyncio
import logging
import yaml
from typing import Annotated, Any, Dict, List, Literal

from autogen_core import (
    AgentId,
    AgentRuntime,
    DefaultTopicId,
    MessageContext,
    RoutedAgent,
    FunctionCall,
    try_get_known_serializers_for_type,
    default_subscription,
    message_handler,
)
from autogen_core.model_context import BufferedChatCompletionContext, ChatCompletionContext
from autogen_core.models import (
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
    UserMessage,
    FunctionExecutionResult,
)
from autogen_core.tool_agent import ToolAgent, tool_agent_caller_loop
from autogen_core.tools import FunctionTool, Tool, ToolSchema

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from chess import BLACK, SQUARE_NAMES, WHITE, Board, Move
from chess import piece_name as get_piece_name
from pydantic import BaseModel

import chess.svg

class TextMessage(BaseModel):
    source: str
    content: str


@default_subscription
class PlayerAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        instructions: str,
        model_client: ChatCompletionClient,
        model_context: ChatCompletionContext,
        tool_schema: List[ToolSchema] | List[Tool],
        tool_agent_type: str,
    ) -> None:
        super().__init__(description=description)
        self._system_messages: List[LLMMessage] = [SystemMessage(content=instructions)]
        self._model_client = model_client
        self._tool_schema = tool_schema
        self._tool_agent_id = AgentId(tool_agent_type, self.id.key)
        self._model_context = model_context

    @message_handler
    async def handle_message(self, message: TextMessage, ctx: MessageContext) -> None:
        # Add the user message to the model context.
        print(f"handle message1")
        await self._model_context.add_message(UserMessage(content=message.content, source=message.source))
        # Run the caller loop to handle tool calls.
        print(f"handle message2")
        messages = await tool_agent_caller_loop(
            caller=self,
            tool_agent_id=self._tool_agent_id,
            model_client=self._model_client,
            input_messages=self._system_messages + (await self._model_context.get_messages()),
            tool_schema=self._tool_schema,
            cancellation_token=ctx.cancellation_token,
        )
        print(f"handle message3")

        stop = False
        # Add the assistant message to the model context.
        for msg in messages:
            await self._model_context.add_message(msg)
            if "Game over" in msg.content: 
                stop = True
        
        if stop:
            return
        
        # Publish the final response.
        assert isinstance(messages[-1].content, str)
        await self.publish_message(TextMessage(content=messages[-1].content, source=self.id.type), DefaultTopicId())


def validate_turn(board: Board, player: Literal["white", "black"]) -> str:
    """Validate that it is the player's turn to move."""
    last_move = board.peek() if board.move_stack else None
    if last_move is not None:
        if player == "white" and board.color_at(last_move.to_square) == WHITE:
            return "It is not your turn to move. Wait for black to move."
        if player == "black" and board.color_at(last_move.to_square) == BLACK:
            return "It is not your turn to move. Wait for white to move."
    elif last_move is None and player != "white":
        return "It is not your turn to move. Wait for white to move first."
    
    return ""


def get_legal_moves_board(
    board: Board, player: Literal["white", "black"]
) -> Annotated[str, "A list of legal moves in UCI format."]:
    """Get legal moves for the given player."""
    res = validate_turn(board, player)
    if res != "":
        return res
    legal_moves = list(board.legal_moves)
    if player == "black":
        legal_moves = [move for move in legal_moves if board.color_at(move.from_square) == BLACK]
    elif player == "white":
        legal_moves = [move for move in legal_moves if board.color_at(move.from_square) == WHITE]
    else:
        raise ValueError("Invalid player, must be either 'black' or 'white'.")
    if not legal_moves:
        return "No legal moves. The game is over."

    return "Possible moves are: " + ", ".join([move.uci() for move in legal_moves])

def get_board(board: Board) -> str:
    """Get the current board state."""
    if board.is_game_over():
        outcome = board.outcome()
        print(f"game outcome: {outcome}")
        result = "White wins!" if board.result() == "1-0" else "Black wins!" if board.result() == "0-1" else "Draw!"
        return (f"Game over! Result: {result}")
    return str(board)

def make_move_board(
    board: Board,
    player: Literal["white", "black"],
    thinking: Annotated[str, "Thinking for the move."],
    move: Annotated[str, "A move in UCI format."],
) -> Annotated[str, "Result of the move."]:
    """Make a move on the board."""
    validate_turn(board, player)
    new_move = Move.from_uci(move)
    try:
        board.push(new_move)
    except Exception as e:
        return f"Invalid move: {move}, reason: {str(e)}"
    
    # Print the move.
    print("-" * 50)
    print("Player:", player)
    print("Move:", new_move.uci())
    print("Thinking:", thinking)
    print("Board:")
    print(board.unicode(borders=True))

    svg_board = chess.svg.board(board=board)
    with open("chessboard.svg", "w") as file:
        file.write(svg_board)

    # Get the piece name.
    piece = board.piece_at(new_move.to_square)
    if piece is None:
        return f"Invalid move: {move}"
    assert piece is not None
    piece_symbol = piece.unicode_symbol()
    piece_name = get_piece_name(piece.piece_type)
    if piece_symbol.isupper():
        piece_name = piece_name.capitalize()
    return f"Moved {piece_name} ({piece_symbol}) from {SQUARE_NAMES[new_move.from_square]} to {SQUARE_NAMES[new_move.to_square]}."


from aip_chain.chain import membase_chain, membase_id
import os
membase_task_id = os.getenv('MEMBASE_TASK_ID')
if not membase_task_id or membase_task_id == "":
    print("'MEMBASE_TASK_ID' is not set, user defined")
    raise Exception("'MEMBASE_TASK_ID' is not set, user defined")

tool_agent_type = membase_task_id

async def board_tool(runtime: AgentRuntime) -> None:  # type: ignore
    """Create agents for a chess game and return the group chat."""

    # Create the board.
    board = Board()
    svg_board = chess.svg.board(board=board)
    with open("chessboard.svg", "w") as file:
        file.write(svg_board)

    def get_legal_moves(role_type: Annotated[str, "Role type: white or black"]) -> str:
        print("get legal moves")
        return get_legal_moves_board(board, role_type)

    def make_move(
        role_type: Annotated[str, "Role type: white or black"],
        thinking: Annotated[str, "Thinking for the move"],
        move: Annotated[str, "A move in UCI format"],
    ) -> str:
        return make_move_board(board, role_type, thinking, move)

    def get_board_text() -> Annotated[str, "The current board state"]:
        return get_board(board)

    chess_tools: List[Tool] = [
        FunctionTool(
            get_legal_moves,
            name="get_legal_moves",
            description="Get legal moves.",
        ),
        FunctionTool(
            make_move,
            name="make_move",
            description="Make a move.",
        ),
        FunctionTool(
            get_board_text,
            name="get_board",
            description="Get the current board state.",
        ),
    ]

    # Register the agents.
    await ToolAgent.register(
        runtime,
        tool_agent_type,
        lambda: ToolAgent(description="Tool agent for chess game.", tools=chess_tools),
    )

async def chess_game(typ: str , runtime: AgentRuntime, model_config: Dict[str, Any]) -> None:  # type: ignore
    """Create agents for a chess game and return the group chat."""

    def get_legal_moves(role_type: Annotated[str, "Role type: white or black"]) -> str:
        return ""

    def make_move(
        role_type: Annotated[str, "Role type: white or black"],
        thinking: Annotated[str, "Thinking for the move"],
        move: Annotated[str, "A move in UCI format"],
    ) -> str:
        return ""

    def get_board_text() -> Annotated[str, "The current board state"]:
        return ""

    chess_tools: List[Tool] = [
        FunctionTool(
            get_legal_moves,
            name="get_legal_moves",
            description="Get legal moves.",
        ),
        FunctionTool(
            make_move,
            name="make_move",
            description="Make a move.",
        ),
        FunctionTool(
            get_board_text,
            name="get_board",
            description="Get the current board state.",
        ),
    ]

    model_client = ChatCompletionClient.load_component(model_config)

    ins = "You are a chess player and you play as " + typ + ". Use the tool 'get_board' and 'get_legal_moves' to get the legal moves and 'make_move' to make a move. Stop response if game is over. "
 
    agentid = membase_id
    await PlayerAgent.register(
        runtime,
        agentid,
        lambda: PlayerAgent(
            description="Player playing role as: "+ typ,
            instructions=ins,
            model_client=model_client,
            model_context=BufferedChatCompletionContext(buffer_size=1),
            tool_schema=[tool.schema for tool in chess_tools],
            tool_agent_type=tool_agent_type,
        ),
    )


from aip_chain.chain import membase_chain, membase_id

async def main(typ: str, model_config: Dict[str, Any]) -> None:
    """Main Entrypoint."""

    membase_chain.register(membase_id)
    print(f"{membase_id} is register onchain")

    if typ == "board":
        membase_chain.register(membase_task_id)
        print(f"{membase_task_id} is register onchain")

    runtime = GrpcWorkerAgentRuntime('localhost:50060')
    runtime.add_message_serializer(try_get_known_serializers_for_type(FunctionCall))
    runtime.add_message_serializer(try_get_known_serializers_for_type(FunctionExecutionResult))
    runtime.add_message_serializer(try_get_known_serializers_for_type(TextMessage))
    await runtime.start()

    if typ == "board":
        await board_tool(runtime)
    else:
        await chess_game(typ, runtime, model_config)

    # Publish an initial message to trigger the group chat manager to start
    # orchestration.
    # Send an initial message to player white to start the game.
    if typ == 'board':
        rolename = input("input role: ")

        await runtime.send_message(
            TextMessage(content="Game started, white player your move.", source="System"),
            AgentId(rolename, "default"),
        )
    
    await runtime.stop_when_signal()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a chess game between two agents.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument(
        "--model-config", type=str, help="Path to the model configuration file.", default="model_config.yml"
    )
    parser.add_argument(
        "--role", type=str, help="agent role: black, white or board", default="board"
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("autogen_core").setLevel(logging.DEBUG)
        file_name = "chess_game_" + args.role + ".log"
        handler = logging.FileHandler(file_name)
        logging.getLogger("autogen_core").addHandler(handler)

    with open(args.model_config, "r") as f:
        model_config = yaml.safe_load(f)

    asyncio.run(main(args.role, model_config))
