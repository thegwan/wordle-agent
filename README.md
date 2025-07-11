# Wordle Agent

A Wordle-playing AI that combines browser automation (via Playwright) with LLM-based reasoning to solve the daily Wordle. It supports two modes:

- **Wordle Workflow:** The LLM only guesses the next word. The system (plain old Python code) controls the game loop, handles invalid guesses, and manages all browser interactions. This is a classic "AI workflow" where the LLM has no agency over the control flow.
- **Wordle Agent:** The LLM is given a set of tools (guess word, clear word, read board, end game) and decides which tool to use at each step. The LLM receives the full action/result history and can reason about when to guess, clear, read, or end the game. This mode gives the LLM more autonomy, but is more brittle and less reliable than the workflow.

⚠️ This is a prototype meant for experimentation. It has no automated tests or evals and will definitely break if the Wordle site changes. 


## Quick Start
This demo uses the OpenAI Responses API with gpt-4.1-mini. Feel free to swap it out with your favorite model.

### Setup
```bash
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

The script will open a Chromium browser window, navigate to Wordle, and start playing automatically. You'll be able to see the clicks and read the LLM's reasoning steps in the terminal.

## Agent Modes
- **WordleWorkflow:**
  - LLM only outputs the next guess (e.g., `ANSWER: CRANE`).
  - System handles all browser actions, feedback parsing, and control flow.
  - More robust and reliable for Wordle.

- **WordleAgent:**
  - LLM receives a list of available tools and the full action/result history.
  - LLM decides which tool to call (guess, clear, read, end) at each step.
  - More "agentic" but more prone to errors and less reliable for this task, unless
    you swap out the model for a reasoning model (e.g., o3-mini)

You can switch between modes by changing the agent class instantiated in `main.py`:
```python
from wordle_workflow import WordleWorkflow
from wordle_agent import WordleAgent
# ...
# agent = WordleWorkflow(page)  # Low-agency workflow
agent = WordleAgent(page)       # More agentic
```



