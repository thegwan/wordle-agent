# Wordle Agent with LLM Integration

An automated Wordle player that uses OpenAI's GPT-4 to make intelligent guesses based on game history and results.

## Features

- 🤖 **LLM-Powered Guessing**: Uses OpenAI GPT-4 to make intelligent word choices
- 🎯 **Game State Tracking**: Maintains history of all guesses and their results
- 🔄 **Retry Logic**: Handles invalid words and retries with different choices
- 📸 **Screenshot Capture**: Takes descriptive screenshots at each step
- 🎮 **Full Automation**: Plays complete Wordle games automatically

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up OpenAI API Key

You need an OpenAI API key to use the LLM features:

```bash
export OPENAI_API_KEY="your-openai-api-key-here"
```

Or create a `.env` file:
```
OPENAI_API_KEY=your-openai-api-key-here
```

### 3. Install Playwright Browsers

```bash
playwright install chromium
```

## Usage

Run the Wordle agent:

```bash
python main.py
```

The agent will:
1. Open Wordle in a browser
2. Use GPT-4 to make intelligent guesses based on game history
3. Track all guesses and their results (green/yellow/gray tiles)
4. Take screenshots at each step
5. Handle invalid words with retry logic

## How It Works

### LLM Integration
- **Context Building**: Creates rich prompts with game history, showing previous guesses with color-coded results
- **Intelligent Guessing**: GPT-4 analyzes patterns and chooses optimal words
- **Validation**: Ensures LLM responses are valid 5-letter words
- **Fallback**: Uses random selection if LLM fails or returns invalid words

### Game State Tracking
- Maintains history of all valid guesses and their results
- Formats results as: `C(green) R(yellow) A(gray) N(gray) E(gray)`
- Provides context about remaining guesses and available words

### Word Pool Management
- Uses sampling without replacement to avoid repeating words
- 15 valid 5-letter words in the pool
- Resets pool if all words are used

## Configuration

You can modify the word pool in `main.py`:
```python
available_words = ["crane", "slate", "bread", "quick", "jumps", "vivid", "zebra", "piano", "smile", "beach", "dream", "flame", "humps", "horse", "stump"]
```

## Screenshots

The agent takes descriptive screenshots:
- `wordle_after_play_button.png` - After clicking Play
- `wordle_game_board_loaded.png` - Game board ready
- `wordle_round_X_after_guess_WORD.png` - After each guess
- `wordle_round_X_retry_after_guess_WORD.png` - After retry attempts
- `wordle_game_won.png` - Game victory
- `wordle_game_lost.png` - Game defeat

## Troubleshooting

- **API Key Issues**: Ensure `OPENAI_API_KEY` is set correctly
- **Invalid Words**: The agent will retry with different words if one is rejected
- **Network Issues**: Check your internet connection for API calls
- **Browser Issues**: Make sure Playwright browsers are installed

## Cost Considerations

- GPT-4 API calls cost money per token
- Each game typically uses 6-12 API calls
- Consider using `gpt-3.5-turbo` for cheaper/faster responses