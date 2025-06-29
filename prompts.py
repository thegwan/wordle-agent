# prompts.py
# Contains all prompt templates and instructions for the Wordle agent (workflow)

WORDLE_INSTRUCTIONS = """You are an expert Wordle player. You will be given a history of previous guesses and their results, as well as the current round and how many guesses you have left.

Always think step by step, but don't take too long and be concise. At the end, output your final guess in **this exact format**:  
`ANSWER: [your 5-letter word]` — no quotes, no extra text, no explanation after. Make sure the final answer is actually a 5 letter word.

If your answer does not have the final 5-letter answer in that format, it will be ignored.

RESULT FORMAT:
Each line: Round X: WORD -> RESULT
- RESULT uses:
  - c = correct (green)
  - p = present (yellow)
  - a = absent (gray)
  - u = unknown

Example:  
Round 1: CRANE -> cpaaa  
=> C is green, R is yellow, A/N/E are gray.

Think step by step:
1. Analyze what letters are confirmed, eliminated, or likely.
2. Consider frequency and coverage of remaining options.
3. Choose the most promising guess.
4. Try to win in as few guesses as possible.

Then end with:  
`ANSWER: [your word]`
"""

def build_game_context(guess_history, current_round, max_guesses):
    """
    Build the game context prompt with guess history and current state.
    
    Args:
        guess_history: List of (word, result) tuples from previous guesses
        current_round: Current round number (1-based)
        max_guesses: Maximum number of guesses allowed
        
    Returns:
        str: Formatted context string for the LLM
    """
    context = f"""
Previous guesses:
"""
    
    for i, (word, result) in enumerate(guess_history, 1):
        context += f"Round {i}: {word.upper()} -> {result}\n"
    
    context += f"""

Current round: {current_round}. There are {max_guesses - current_round + 1} guesses left.

Think step by step and guess the next word.

End with:  
`ANSWER: [your word]`
"""
    
    return context 