import argparse
import asyncio
import logging
import yaml
import random
import time
from typing import Annotated, Any, Dict, List

from autogen_core import (
    AgentId,
    AgentRuntime,
    MessageContext,
    RoutedAgent,
    try_get_known_serializers_for_type,
    message_handler,
)
from autogen_core.model_context import UnboundedChatCompletionContext, ChatCompletionContext
from autogen_core.models import (
    LLMMessage,
    SystemMessage,
    UserMessage,
)

from autogen_ext.runtimes.grpc import GrpcWorkerAgentRuntime

from common import TextMessage, Player

from aip_agent.chain.chain import membase_chain, membase_id
import os
membase_task_id = os.getenv('MEMBASE_TASK_ID')
if not membase_task_id or membase_task_id == "":
    print("'MEMBASE_TASK_ID' is not set, user defined")
    raise Exception("'MEMBASE_TASK_ID' is not set, user defined")

MAX_WEREWOLF_DISCUSSION_ROUND = 3
MAX_GAME_ROUND = 1

class WolfGame:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.healing = True
        self.poison = True
        self.players = [
            Player(name="", type="wolf", state="unregistered"),
            Player(name="", type="wolf", state="unregistered"),
            Player(name="", type="village", state="unregistered"),
            Player(name="", type="village", state="unregistered"),
            Player(name="", type="seer", state="unregistered"),
            Player(name="", type="witch", state="unregistered")
        ]
        self.runtime = runtime
        self.unregister = [0,1,2,3,4,5]

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

    def get_survive(self):
        players = ", ".join(player.name for player in self.players if player.state == "alive")
        return players

    def get_wolves(self):
        wolves = ", ".join(player.name for player in self.players if player.type == "wolf")
        return wolves

    def mark_dead(self, name: str):
        for player in self.players:
            if player.name.lower() == name.lower():
               player.state = "dead"
               return player.name
        return ""

    def check_win(self):
        wolf_cnt = 0
        alive_cnt = 0
        for player in self.players:
            if player.state == "alive":
                alive_cnt+=1
                if player.type == "wolf":
                    wolf_cnt+=1

        if wolf_cnt*2 >= alive_cnt:
            return "Game over: wolf win"    

        if wolf_cnt == 0:
            return "Game over: village win"

        return ""            

    async def broadcast(self, msg: TextMessage):
        results: List[TextMessage] = []
        for player in self.players:
            if player.state != "alive":
                continue
            res = await self.runtime.send_message(msg, AgentId(player.name, membase_task_id), sender=AgentId(membase_id, membase_task_id))
            results.append(res)
        return results

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

    async def collect_votes(self, votes: List[TextMessage]) -> str:
        """Count votes and return the name of the player with the most votes"""
        print(f'collect_votes: {votes}')
        vote_count = {}
        for vote in votes:
            if not vote.content:
                continue
            # Assume the vote content is the player name
            voted_player = vote.content.strip().lower()
            vote_count[voted_player] = vote_count.get(voted_player, 0) + 1
        
        if not vote_count:
            return ""
            
        # Find the player(s) with the most votes
        max_votes = max(vote_count.values())
        most_voted = [player for player, count in vote_count.items() if count == max_votes]
        
        # If there's a tie, randomly choose one
        return random.choice(most_voted) if most_voted else ""

    async def process_wolf_vote(self, votes: List[TextMessage]) -> str:
        """Process werewolves' night vote"""
        # Only count votes from alive werewolves

        for vote in votes:
            for player in self.players:
                if player.name.lower() in vote.content:
                    vote.content = player.name
                    break

        wolf_votes = []
        for vote in votes:
            for player in self.players:
                if player.name == vote.source and player.type == "wolf" and player.state == "alive":
                    wolf_votes.append(vote)
                    break
        return await self.collect_votes(wolf_votes)

    async def process_day_vote(self, votes: List[TextMessage]) -> str:
        """Process daytime vote from all players"""
        # Count votes from all alive players
        valid_votes = []
        for vote in votes:
            for player in self.players:
                if player.name == vote.source and player.state == "alive":
                    valid_votes.append(vote)
                    break
        return await self.collect_votes(valid_votes)

class ModeratorAgent(RoutedAgent):
    def __init__(
        self,
        description: str,
        instructions: str,
        model_context: ChatCompletionContext,
        game: WolfGame,
    ) -> None:
        super().__init__(description=description)
        self._system_messages: List[LLMMessage] = [SystemMessage(content=instructions)]
        self._model_context = model_context
        self.game = game
        print(f"=== start agent: {self.id}")

    @message_handler
    async def handle_message(self, message: TextMessage, ctx: MessageContext) -> TextMessage:
        """Handle incoming messages based on their type."""
        print(f"handle message {message}")
        await self._model_context.add_message(UserMessage(content=message.content, source=message.source))
        # Handle registration
        if message.type == "register":
            playertype = self.game.register(message.source)
            await self._model_context.add_message(UserMessage(content=playertype, source=self.id.type))
            return TextMessage(
                type="response",
                content=playertype,
                source=self.id.type
            )

        print(f"handle message done")

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
    game = WolfGame(runtime=runtime)

    ins = ""
    moderator_id = membase_id
    await ModeratorAgent.register(
        runtime,
        moderator_id,
        lambda: ModeratorAgent(
            description="You are moderator in were wolf game",
            instructions=ins,
            model_context=UnboundedChatCompletionContext(),
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

    # Send secret information to werewolves about their teammates
    wolves = game.get_wolves()
    msg = TextMessage(
            type="important_info", 
            content="The wolves are: " + wolves,
            source=moderator_id
        )
    await game.send_message("wolf", msg)
    
    # Main game loop - continues for MAX_GAME_ROUND rounds or until game ends
    for _ in range(1, MAX_GAME_ROUND + 1):
        # Announce new night and surviving players
        content = "New night comes. There are survive players: " + game.get_survive()
        print(content)

        msg = TextMessage(type="system_notice", content=content, source=moderator_id)
        await game.send_message("all", msg)

        # Night phase begins
        # Step 1: Werewolves vote for elimination
        wolves = game.get_wolves()
        msg = TextMessage(
            type="night_kill", 
            content="Which player do you vote to eliminate?",
            source=moderator_id
        )
        res = await game.send_message("wolf", msg)
        print(f"night_kill: {res}")
        dead_player = await game.process_wolf_vote(res)
        print(f"night_kill dead: {dead_player}")
        content = "The player with the most votes is: " + dead_player
        msg = TextMessage(type="system_notice", content=content, source=moderator_id)
        await game.send_message("wolf", msg)

        # Step 2: Witch's turn - can save or poison
        tonight_saving = False
        poison_player = ""
        if game.healing and game.players[-1].state == "alive":
            # Witch decides whether to use healing potion
            content = "You're the witch. Tonight one player is eliminated. Would you like to resurrect this player?"
            msg = TextMessage(type="save", content=content, source=moderator_id)
            responses = await game.send_message("witch", msg)
            if responses and responses[0].content.lower() == "yes":
                tonight_saving = True
                game.healing = False  # Healing potion is used
                dead_player = ""  # Cancel the kill

            # If no healing was used, witch can choose to use poison
            if not tonight_saving and game.poison:
                content = "Would you like to eliminate one player? If yes, specify the player name."
                msg = TextMessage(type="poison", content=content, source=moderator_id)
                responses = await game.send_message("witch", msg)
                if responses and responses[0].content.lower() != "no":
                    poison_player = responses[0].content.strip()
                    if poison_player != "":
                        game.poison = False  # Poison potion is used

        # Step 3: Seer's investigation  
        if game.players[-1].state == "alive":
            survives = game.get_survive()
            content = "You're the seer. Which player in: " + survives + " would you like to check tonight?"
            msg = TextMessage(type="divine", content=content, source=moderator_id)
            responses = await game.send_message("seer", msg)
            
            # Process seer's investigation result
            check_player = ""
            check_role = ""
            if responses and responses[0].content:
                check_player = responses[0].content.strip().lower()
                for player in game.players:
                    if player.name.lower() in check_player:
                        check_player = player.name
                        check_role = player.type
                        break
                        
            if check_player and check_role:
                content = f"The role of {check_player} is {check_role}"
                msg = TextMessage(type="system_notice", content=content, source=moderator_id)
                await game.send_message("seer", msg)

        # Update player states after night actions
        deads = []
        if dead_player != "":
            dead_player = game.mark_dead(dead_player)
        if dead_player != "":    
            deads.append(dead_player)
        if poison_player != "":
            poison_player = game.mark_dead(poison_player)
        if poison_player != "":
            deads.append(poison_player)
        
        # Check win conditions
        res = game.check_win()
        if res != "":
            print(res)
            msg = TextMessage(type="system_notice", content=res, source=moderator_id)
            await game.broadcast(msg)
            break
            
        # Announce night phase results
        if len(deads) == 0:
            content = "The day is coming, all the players open your eyes. Last night is peaceful, no player is eliminated."
        else:
            content = "The day is coming, all the players open your eyes. Last night, the following player(s) has been eliminated: " + ", ".join(deads)
        msg = TextMessage(type="system_notice", content=content, source=moderator_id)
        await game.broadcast(msg)

        # Day phase begins
        # Step 1: Discussion phase
        content = "Now the alive players are: " + game.get_survive() + ". Given the game rules and your role, based on the situation and the information you gain, what do you want to say to others?"
        msg = TextMessage(type="day_discuss", content=content, source=moderator_id)
        results: List[TextMessage] = []
        for player in game.players:
            if player.state != "alive":
                continue
            
            res = await game.runtime.send_message(msg, AgentId(player.name, membase_task_id), sender=AgentId(membase_id, membase_task_id))
            results.append(res)
            # Broadcast each player's discussion message to all players
            res.type = "system_notice"
            await game.broadcast(res)
        
        # Step 2: Voting phase
        content = "It's time to vote. Which player do you suspect to be a wolf?"
        msg = TextMessage(type="day_vote", content=content, source=moderator_id)
        votes = await game.send_message("all", msg)

        # Process voting results
        vote_player = await game.process_day_vote(votes)
        if vote_player != "":
            content = f"The voting result is: Player {vote_player} has been eliminated."
            msg = TextMessage(type="system_notice", content=content, source=moderator_id)
            await game.broadcast(msg)
            game.mark_dead(vote_player)

        # Check win conditions after day phase
        res = game.check_win()
        if res != "":
            print(res)
            msg = TextMessage(type="system_notice", content=res, source=moderator_id)
            await game.broadcast(msg)
            break

        return

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