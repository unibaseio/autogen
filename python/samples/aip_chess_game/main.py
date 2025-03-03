"""This is an example of simulating a chess game with two agents
that play against each other, using tools to reason about the game state
and make moves. The agents subscribe to the default topic and publish their
moves to the default topic."""

import argparse
import asyncio
import logging
import random
import time
import yaml
from typing import Annotated, Any, Dict, List, Literal

from autogen_core import (
    AgentId,
    AgentRuntime,
    MessageContext,
    RoutedAgent,
    try_get_known_serializers_for_type,
    message_handler,
)

from autogen_core.models import (
    LLMMessage,
    SystemMessage,
)

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from chess import BLACK, SQUARE_NAMES, WHITE, Board, Move # type: ignore
from chess import piece_name as get_piece_name
from pydantic import BaseModel

import chess.svg

class TextMessage(BaseModel):
    source: str
    content: str

from aip_agent.chain.chain import membase_chain, membase_id
from aip_agent.memory.message import Message
from aip_agent.memory.memory import MemoryBase
from aip_agent.memory.buffered_memory import BufferedMemory

import os
membase_task_id = os.getenv('MEMBASE_TASK_ID')
if not membase_task_id or membase_task_id == "":
    print("'MEMBASE_TASK_ID' is not set, user defined")
    raise Exception("'MEMBASE_TASK_ID' is not set, user defined")


from common import Player, TextMessage
from prompt import parse_response

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

class ChessGame:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.healing = True
        self.poison = True
        self.players = [
            Player(name="", type="white", state="unregistered"),
            Player(name="", type="black", state="unregistered"),
        ]
        self.runtime = runtime
        self.unregister = [0,1]
        self.white = True
        self.board = Board()
        svg_board = chess.svg.board(board=self.board)
        with open("chessboard.svg", "w") as file:
            file.write(svg_board)

    def register(self, name: str) -> str:
        """Register a new player to the game.
        
        Args:
            name: The name of the player to register
            
        Returns:
            str: The assigned role type if registration successful, empty string if failed
            
        Note:
            Registration will fail if:
            - No available slots (all roles taken)
            - Player name already registered
        """
        # Check if player already registered
        for player in self.players:
            if player.name.lower() == name.lower():
                return ""  # Player already registered
                
        # Check if any slots available
        if len(self.unregister) == 0:
            return ""  # No available slots
            
        # Assign random available role
        choosed = random.choice(self.unregister)
        self.players[choosed].state = "alive"
        self.players[choosed].name = name
        self.unregister.remove(choosed)
        return self.players[choosed].type
    
    async def send_message(self, typ: str, msg: TextMessage) -> List[TextMessage]:
        """Send message to players of specific type or all players.
        
        Args:
            typ: Player type to send to, or "all" for all players
            msg: Message to send
            
        Returns:
            List[TextMessage]: List of response messages from alive players of the specified type
        """
        results: List[TextMessage] = []
        for player in self.players:
            if player.state != "alive":
                continue
            if player.type != typ and typ != "all":
                continue
            try:
                res = await self.runtime.send_message(msg, AgentId(player.name, membase_task_id), sender=AgentId(membase_id, membase_task_id))
                if res and isinstance(res, TextMessage):
                    results.append(res)
            except Exception as e:
                print(f"Error sending message to {player.name}: {e}")
        return results
    
    def make_move(self, player: Literal["white", "black"], thinking: str, move: str):
        return make_move_board(self.board, player, thinking, move)
        
    def check_game_over(self):
        if self.board.is_game_over():
            outcome = self.board.outcome()
            print(f"game outcome: {outcome}")
            result = "White wins!" if self.board.result() == "1-0" else "Black wins!" if self.board.result() == "0-1" else "Draw!"
            return (f"Game over! Result: {result}")
        return None

    def get_winner(self):
        if self.board.is_game_over():
            result = self.players[0].name if self.board.result() == "1-0" else self.players[1].name if self.board.result() == "0-1" else ""
            return result
        return None

    def get_board_step(self, player: Literal["white", "black"]):
        boardtext = get_board(self.board)
        step = get_legal_moves_board(self.board, player)
        return "Board: " + boardtext + "\n" + step

class ModeratorAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        instructions: str,
        memory: MemoryBase,
        game: ChessGame,
    ) -> None:
        super().__init__(description=description)
        self._memory = memory
        self.game = game
        print(f"=== start agent: {self.id}")

    @message_handler
    async def handle_message(self, message: TextMessage, ctx: MessageContext) -> TextMessage:
        """Handle incoming messages based on their type."""
        logging.debug(f"handle message {message}")
        self._memory.add(Message(content=message.content, role="user", name=message.source))
        # Handle registration
        if message.type == "register":
            playertype = self.game.register(message.source)
            self._memory.add(Message(content=playertype, role="assistant", name=self.id.type))
            return TextMessage(
                type="response",
                content=playertype,
                source=self.id.type
            )


MAX_GAME_ROUND = 100

async def main() -> None:
    membase_chain.register(membase_id)
    print(f"{membase_id} is register onchain")
    time.sleep(3)
   
    membase_chain.createTask(membase_task_id, 1_000_000)
    print(f"task: {membase_task_id} is register onchain")
    time.sleep(3)
    
    # start the game
    runtime = GrpcWorkerAgentRuntime('localhost:50060')
    runtime.add_message_serializer(try_get_known_serializers_for_type(TextMessage))
    await runtime.start()

    print("start the wolf game")
    game = ChessGame(runtime=runtime)

    memory=BufferedMemory(persistence_in_remote=True)

    ins = ""
    moderator_id = membase_id
    await ModeratorAgent.register(
        runtime,
        moderator_id,
        lambda: ModeratorAgent(
            description="You are moderator in were wolf game",
            instructions=ins,
            memory=memory,
            game=game,
        ),
    )

    # Wait for player registration with timeout
    max_wait_time = 300  # 5 minutes timeout
    start_time = time.time()
    
    while len(game.unregister) > 0:
        if time.time() - start_time > max_wait_time:
            print("Registration timeout, game cannot start")
            return
        print(f"Waiting for {len(game.unregister)} more players to register...")
        await asyncio.sleep(5)  # Use asyncio.sleep instead of time.sleep to avoid blocking

    time.sleep(3)
    print("All players registered, game starting...")

    for i in range(1, MAX_GAME_ROUND + 1):
        game_over = game.check_game_over()
        if game_over:
            print(game_over)
            break

        player = "white" if game.white else "black"
        # get the board step    
        board_step = game.get_board_step(player)
        memory.add(Message(content=board_step, role="user", name=moderator_id))
        msg = TextMessage(
            type="move", 
            content=board_step,
            source=moderator_id
        )
        results = await game.send_message(player, msg)
        for result in results:
            memory.add(Message(content=result.content, role="assistant", name=result.source))
            # result format: thinking: xxx, move: xxx
            thinking, move = parse_response(result.content)
            res = game.make_move(player, thinking, move)
            print("=====", i, player , res)

        # white and black take turns to move
        game.white = not game.white
    
    winner = game.get_winner()
    if winner and winner != "":
        membase_chain.finishTask(membase_task_id, winner)
    else: 
        print(f"Game over, no winner after {MAX_GAME_ROUND/2} rounds")
    await runtime.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a werewolf game")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.WARNING)
        logging.getLogger("autogen_core").setLevel(logging.DEBUG)
        file_name = "wolf_game" + membase_id + ".log"
        handler = logging.FileHandler(file_name)
        logging.getLogger("autogen_core").addHandler(handler)

    asyncio.run(main())