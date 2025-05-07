import logging
from openai import OpenAI
from openai._exceptions import AuthenticationError, OpenAIError

# Configure logging for debugging
logger = logging.getLogger("openai_client")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class OpenAIClient:
    def __init__(self, api_key: str):
        print(f" ********** API Key loaded from environment: {api_key[:30]}")
        self.client = OpenAI(api_key=api_key)

    async def test_openai(self, question: str):
        try:
            logger.debug(f"Sending question to OpenAI: {question}")
            response = self.client.chat.completions.create(
                model="o4-mini",
                messages=[
                    {"role": "user", "content": question}
                ],
                stream=False
            )

            logger.debug(f"Response received from OpenAI: {response}")
            full_text = response.choices[0].message.content.strip()
            tokens = full_text.split()  # эмуляция токенов по словам

            return {
                "status": "success",
                "tokens": tokens,
                "full_response": full_text,
                "total_tokens": response.usage.total_tokens if response.usage else len(tokens)
            }

        except AuthenticationError:
            logger.error("Invalid OpenAI API key.")
            return {"status": "error", "message": "Invalid OpenAI API key."}
        except OpenAIError as e:
            logger.error(f"OpenAI error: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"OpenAI error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
