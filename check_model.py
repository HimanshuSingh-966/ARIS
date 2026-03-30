import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

print("Available Embedding Models:")
for m in genai.list_models():
    # Filter for models that support embedding
    if 'embedContent' in m.supported_generation_methods:
        print(f" - {m.name}")
