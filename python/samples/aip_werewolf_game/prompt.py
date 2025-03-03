"""Prompt templates for werewolf game."""


def get_game_prompt(player_name:str, player_role: str) -> str:
    """Return the game prompt for werewolf game players.
    
    Returns:
        str: The game prompt describing game rules and roles for wolf.
    """
    prompt = f"""Act as a player in a werewolf game.

PLAYER ROLES:
In werewolf game, players are divided into two wolves, two villagers, one seer and one witch. Note only wolves know who are their teammates.
Wolves: They know their teammates' identities and attempt to eliminate a villager each night while trying to remain undetected.
Villagers: They do not know who the wolves are and must work together during the day to deduce who the wolves might be and vote to eliminate them.
Seer: A villager with the ability to learn the true identity of one player each night. This role is crucial for the villagers to gain information.
Witch: A villager who has a one-time ability to save a player from being eliminated at night (sometimes this is a potion of life) and a one-time ability to eliminate a player at night (a potion of death).

GAME RULE:
The game is consisted of two phases: night phase and day phase. The two phases are repeated until wolf or villager win the game.
1. Night Phase: During the night, the wolves discuss and vote for a player to eliminate. Special roles also perform their actions at this time (e.g., the Seer chooses a player to learn their role, the witch chooses a decide if save the player).
2. Day Phase: During the day, all surviving players discuss who they suspect might be a wolf. No one reveals their role unless it serves a strategic purpose. After the discussion, a vote is taken, and the player with the most votes is "lynched" or eliminated from the game.

VICTORY CONDITION:
For wolves, they win the game if the number of wolves is equal to or greater than the number of remaining villagers.
For villagers, they win if they identify and eliminate all of the wolves in the group.

CONSTRAINTS:
1. This is a conversational game. You should response only based on the conversation history and your strategy.

Your name is {player_name} and you are playing {player_role} in this game."""
    return prompt


def get_response_format(msg_type: str) -> str:
    """Return specific response format based on message type.
    
    Args:
        msg_type: Type of the message:
            - night_kill: Werewolf kill vote
            - divine: Seer's investigation
            - save: Witch's healing potion
            - poison: Witch's poison potion
            - day_discuss: Daytime discussion
            - day_vote: Daytime voting
    
    Returns:
        str: The specific response format instructions
    """
    formats = {
        "night_kill": "Please only specify the name of the player you want to eliminate.",
        "day_vote": "Please only specify the name of the player you suspect to be a werewolf.",
        "save": "Please respond with 'yes' if you want to use the healing potion, or 'no' if not. You donot need to know the dead player's name.",
        "poison": "Please only specify a player name if you want to use the poison, or respond with 'no'.",
        "divine": "Please only specify the name of the player whose identity you want to investigate.",
        "day_discuss": "Please share your suspicions and reasoning concisely. You may choose to reveal your role based on your strategy."
    }
    return formats.get(msg_type, "Please respond according to the game rules and your role.")
