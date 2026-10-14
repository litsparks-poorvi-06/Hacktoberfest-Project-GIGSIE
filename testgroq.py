import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise SystemExit("API key not found. Check your .env file.")

client = Groq(api_key=api_key)

try:
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": "You are Gigsie's business task-planning assistant."
            },
            {
                "role": "user",
                "content": (
                    "A bakery has Rs 800 and two days to promote "
                    "a new menu. Suggest three clear deliverables "
                    "and three questions the owner should answer."
                )
            }
        ],
        max_completion_tokens=1024
    )

    print(response.choices[0].message.content)

except Exception as error:
    print(f"Request failed: {type(error).__name__}: {error}")