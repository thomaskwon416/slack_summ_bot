from slack_handlers.utils import (
    fetch_channel_history_with_threads,
    send_dm_to_user,
)
from services.summarizer import generate_summary
from configs.config import logger


def register_slash_commands(app):
    """
    Register slash command handlers with the Slack Bolt app.
    """

    @app.command("/summarize")
    def handle_summarize(ack, body, client, respond):
        """
        Slash command handler for /summarize.
        Fetches channel messages, generates a summary, and sends the summary to the user via DM.
        """
        ack()  # Acknowledge the slash command
        user_id = body["user_id"]
        channel_id = body["channel_id"]

        logger.info(f"Received /summarize command from user {user_id} in channel {channel_id}.")

        # 1) Fetch channel history
        messages = fetch_channel_history_with_threads(client, channel_id)
        if not messages:
            respond("No messages found in the past 7 days or an error occurred.")
            logger.warning(f"No messages to summarize in channel {channel_id}.")
            return

        # 2) Build a single string from all messages
        conversation_text_lines = []
        for msg in messages:
            line = f"({msg['timestamp']}) {msg['user']}: {msg['text']}"
            conversation_text_lines.append(line)
        conversation_text = "\n".join(conversation_text_lines)

        if not conversation_text:
            respond("No text-based messages found to summarize.")
            logger.warning(f"No text messages found in channel {channel_id}.")
            return

        # 3) Generate summary via CentML/OpenAI
        try:
            summary = generate_summary(conversation_text)
        except Exception as e:
            error_message = f"Sorry, I was unable to summarize the conversation. Error: {e}"
            send_dm_to_user(client, user_id, error_message)
            respond("An error occurred while generating the summary. Check your DM for details.")
            logger.error("Error during summary generation.", exc_info=True)
            return

        # 4) Send DM to the user
        send_dm_to_user(client, user_id, summary)
        respond(f"I've sent a summary of the last 7 days (including threaded replies) to <@{user_id}> via DM.")
        logger.info("Summary DM sent and command handling completed.")
