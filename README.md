# Wordle Agent

Wordle-playing AI that combines DOM reading with LLM-based reasoning to iteratively solve the game. It reads the board state directly from the browser using Playwright, then uses an LLM to guess the next word. It's guided by a structured prompt and explicit CoT, which I find gives similar performance (based on my informal testing) between reasoning and non-reasoning models.

While the model reasons about what words to guess next, it doesn't autonomously decide when to guess, clear, or retry. All game control and tool usage (browser interaction, DOM parsing, retries) are passed off to Plain Old Code. Thus, I'd call this more of an AI workflow than an AI agent.

## Quick Start
This demo uses the OpenAI Responses API with gpt-4.1-mini. Feel free to swap it out with your favorite model.

### Setup
```bash
# Clone the repository
git clone <repository-url>
cd wordle-agent

# Create virtual environment
python -m venv wordle-agent-env
source wordle-agent-env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration
Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_api_key_here
```

### Run
```bash
python main.py
```

The script will open a chromium browser window, navigate to Wordle, and start playing automatically. You'll be able to see the clicks and read the CoT.

