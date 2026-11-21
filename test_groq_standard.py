import asyncio

from groq import AsyncGroq
from app.config import GROQ_API_KEY


client = AsyncGroq(
    api_key=GROQ_API_KEY,
    timeout=45.0
)


async def test_groq_standard():

    print("Testing Groq standard analysis...")

    prompt = """
Analyze Google as a business.

Provide:

1. Business overview
2. Business category
3. Three competitors
4. Five SEO keywords
5. Three target audiences

Keep the response concise.
"""

    try:

        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert business analyst."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )

        print("\nGroq Response:\n")

        print(
            response.choices[0].message.content
        )

    except Exception as error:

        print("\nERROR:")

        print(error)

    finally:

        await client.close()


asyncio.run(test_groq_standard())