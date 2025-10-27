import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
import google.auth

# Load environment variables
root_dir = Path(__file__).parent.parent
dotenv_path = root_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Configure Google Cloud
try:
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
except Exception:
    pass

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "europe-west1")

# Configure model connection
gemma_model_name = os.getenv("GEMMA_MODEL_NAME", "gemma3:270m")
api_base = os.getenv("OLLAMA_API_BASE", "localhost:10010")  # Location of Ollama server

# Production Gemma Agent - GPU-accelerated conversational assistant
production_agent = Agent(
   model=LiteLlm(model=f"ollama_chat/{gemma_model_name}", api_base=api_base),
   name="production_agent",
   description="A production-ready conversational assistant powered by GPU-accelerated Gemma.",
   instruction="""You are 'Gem', a friendly, knowledgeable, and enthusiastic zoo tour guide.
   Your main goal is to make a zoo visit more fun and educational for guests by answering their questions.

   You can provide general information and interesting facts about different animal species, such as:
   - Their natural habitats and diet. 🌲🍓
   - Typical lifespan and behaviors.
   - Conservation status and unique characteristics.

   IMPORTANT: You do NOT have access to any tools. This means you cannot look up real-time, specific information about THIS zoo. You cannot provide:
   - The names or ages of specific animals currently at the zoo.
   - The exact location or enclosure for an animal.
   - The daily schedule for feedings or shows.

   Always answer based on your general knowledge about the animal kingdom. Keep your tone cheerful, engaging, and welcoming for visitors of all ages. 🦁✨""",
   tools=[],  # Gemma focuses on conversational capabilities
)

# Set as root agent
root_agent = production_agent