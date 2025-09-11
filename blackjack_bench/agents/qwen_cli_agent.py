import subprocess
from typing import Any
from ..types import Action # Import Action enum

class QwenCLIAgent:
    def __init__(self, debug_log: bool = False):
        self.debug_log = debug_log

    def act(self, observation: Any, info: Any) -> str:
        player_cards = observation.player.cards
        dealer_up_card = observation.dealer_upcard
        actions = [a.name for a in observation.allowed_actions] # Convert Action enums to strings

        # Format the game state into a prompt for qwen
        # TODO Fix the prompt, actions are wrong and it's not the correct prompt.
        prompt = (
            "Blackjack. Rules: 6 decks, dealer hits soft 17 (H17), blackjack pays 3:2, double on any two, "
            "double after split allowed, resplit to 3 hands, split aces one-card, no surrender.\n"
            f"Dealer upcard: {dealer_up_card[:-1]}.\n"
            f"Your hand: {','.join(c[:-1] for c in player_cards)}.\n"
            "Reply with exactly one word: HIT, STAND, DOUBLE, or SPLIT. No explanations."
        )

        try:
            # Execute the qwen command
            result = subprocess.run(
                ["qwen", "-p", prompt],
                capture_output=True,
                text=True,
                check=True
            )
            raw_output = result.stdout # Store raw output
            action_str = raw_output.strip().lower()
            
            info["llm_raw"] = raw_output # Log raw output always
            
            # Convert string action back to Action enum
            try:
                action_enum = Action[action_str.upper()]
            except KeyError:
                print(f"Warning: Qwen returned an unrecognized action '{action_str}'. Falling back to 'stand'.")
                action_enum = Action.STAND

            if action_enum in observation.allowed_actions:
                return action_enum # Return the Action enum directly
            else:
                print(f"Warning: Qwen returned an invalid action '{action_str}' for current state. Falling back to 'stand'.")
                return Action.STAND # Fallback for invalid actions

        except subprocess.CalledProcessError as e:
            print(f"Error running qwen: {e}")
            print(f"Stderr: {e.stderr}")
            return Action.STAND.name # Fallback on error
        except FileNotFoundError:
            print("Error: 'qwen' command not found. Please ensure Qwen is installed and in your PATH.")
            return Action.STAND.name # Fallback if qwen is not installed
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return Action.STAND.name # Generic fallback
