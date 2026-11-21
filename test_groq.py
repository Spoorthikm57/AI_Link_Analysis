import asyncio
from groq import AsyncGroq

from app.config import GROQ_API_KEY, GROQ_MODEL, GROQ_TIMEOUT_SECONDS


async def main() -> None:
    client = AsyncGroq(
        api_key=GROQ_API_KEY,
        timeout=GROQ_TIMEOUT_SECONDS,
        max_retries=0,
    )

    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": 'Return only this JSON: {"status":"ok"}'}],
            response_format={"type": "json_object"},
            temperature=0,
            max_completion_tokens=64,
        )
        print("Groq API connection successful.")
        print(response.choices[0].message.content)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
