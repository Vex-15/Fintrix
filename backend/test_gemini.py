import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
gemini_key = os.getenv("GEMINI_API_KEY")
print("Key:", gemini_key)

genai.configure(api_key=gemini_key)
model = genai.GenerativeModel("gemini-2.0-flash")

try:
    response = model.generate_content("Hello")
    print(response.text)
except Exception as e:
    import traceback
    traceback.print_exc()
