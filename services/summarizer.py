import json
from services.openai_client import get_openai_client
from configs.config import logger, CENTML_API_KEY
from configs.system_prompts import SUMMARY_SYSTEM_PROMPT


def generate_summary(conversation_text):
    """
    Given raw conversation text, uses the CentML/OpenAI API to generate a summary.
    Returns a string (the summary).
    """
    openai_client = get_openai_client(CENTML_API_KEY)
    logger.info(
        "Sending conversation text to CentML OpenAI for summarization.")

    request_payload = {
        "model":
        "meta-llama/Llama-3.3-70B-Instruct",
        "messages": [{
            "role": "system",
            "content": SUMMARY_SYSTEM_PROMPT.format(conversation_text)
        }],
        "max_tokens":
        30000,
        "temperature":
        0.7
    }

    # Log the API request (sanitized/truncated as needed)
    logger.info("POST Request to CentML OpenAI API:")
    logger.info("URL: https://api.centml.com/openai/v1/chat/completions")
    logger.info("Headers: Authorization: Bearer sk-... (truncated)")
    logger.info(f"Request Payload: {json.dumps(request_payload, indent=2)}")

    response = openai_client.chat.completions.create(**request_payload)
    summary = response.choices[0].message.content
    logger.info("Successfully generated summary.")
    return summary
