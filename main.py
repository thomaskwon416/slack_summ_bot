import os
import datetime
import logging
import json
from openai import OpenAI
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Environment Variables ---
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CENTML_API_KEY = os.environ.get("CENTML_API_KEY")

if not SLACK_SIGNING_SECRET or not SLACK_BOT_TOKEN or not CENTML_API_KEY:
    logger.error("One or more required environment variables are missing.")
    raise ValueError(
        "Missing environment variables: SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN, CENTML_API_KEY"
    )

# --- Slack App and Flask Setup ---
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


def fetch_channel_history_with_threads(client, channel_id):
    """
    Fetch up to 1000 messages (last 7 days), including threaded replies.
    Returns a list of dicts with:
      {
        "user": display_name,
        "timestamp": "YYYY-MM-DD HH:MM:SS",
        "raw_ts": "1671481775.000300",
        "text": "...",
      }
    """

    one_week_ago_ts = str(
        (datetime.datetime.now() - datetime.timedelta(days=7)).timestamp())
    try:
        # 1) Fetch main channel messages
        response = client.conversations_history(channel=channel_id,
                                                oldest=one_week_ago_ts,
                                                limit=1000)
        raw_messages = response.get("messages", [])
        logger.info(
            f"Fetched {len(raw_messages)} top-level messages from channel {channel_id}."
        )

        # Gather unique user IDs to build a display-name cache
        user_ids = set()
        for msg in raw_messages:
            if "user" in msg:
                user_ids.add(msg["user"])

        # Build user cache { user_id: display_name }
        user_cache = {}
        for uid in user_ids:
            try:
                user_info = client.users_info(user=uid)
                profile = user_info["user"]["profile"]
                display_name = profile.get("display_name") or profile.get(
                    "real_name") or uid
                user_cache[uid] = display_name
            except Exception as e:
                logger.error(
                    f"Unable to fetch display name for user {uid}: {e}",
                    exc_info=True)
                user_cache[uid] = uid  # fallback to user ID

        # 2) Iterate over top-level messages and fetch threaded replies
        all_messages = []
        for top_msg in raw_messages:
            # Add the parent (top-level) message
            all_messages.append(process_slack_message(top_msg, user_cache))

            # If there's a thread, fetch all replies
            if top_msg.get("reply_count", 0) > 0:
                thread_ts = top_msg["ts"]  # The parent message's ts
                try:
                    replies_resp = client.conversations_replies(
                        channel=channel_id,
                        ts=thread_ts,
                        oldest=one_week_ago_ts,
                        limit=1000)
                    thread_messages = replies_resp.get("messages", [])

                    # Skip the first item if you don't want the original message repeated
                    # The first item in `conversations_replies` is the parent message
                    if len(thread_messages) > 1:
                        for reply_msg in thread_messages[1:]:
                            all_messages.append(
                                process_slack_message(reply_msg, user_cache))
                except Exception as e:
                    logger.error(
                        f"Error fetching thread replies for ts={thread_ts}: {e}",
                        exc_info=True)

        # 3) Sort everything by raw Slack timestamp (ascending)
        # Slack's 'ts' is a float-like string "1671481775.000300"
        # We'll store numeric version in 'raw_ts' so sorting is easy
        all_messages.sort(key=lambda m: float(m["raw_ts"]))
        return all_messages

    except Exception as e:
        logger.error(
            f"Error fetching channel history or threaded replies: {e}",
            exc_info=True)
        return []


def process_slack_message(msg, user_cache):
    """
    Helper function to build a consistent dictionary from a Slack message.
    """
    user_id = msg.get("user", "unknown_user")
    text = msg.get("text", "")
    raw_ts = msg.get("ts", "0")

    # Convert Slack timestamp to human-readable
    try:
        human_readable_ts = datetime.datetime.fromtimestamp(
            float(raw_ts)).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        human_readable_ts = raw_ts  # fallback if parsing fails

    display_name = user_cache.get(user_id, user_id)

    return {
        "user": display_name,
        "timestamp": human_readable_ts,
        "raw_ts": raw_ts,  # keep raw for sorting
        "text": text
    }


def send_dm_to_user(client, user_id, text):
    """
    Open a DM channel with a user and send a given text message.
    """
    try:
        im_response = client.conversations_open(users=user_id)
        dm_channel = im_response["channel"]["id"]
        client.chat_postMessage(channel=dm_channel, text=text)
        logger.info(f"Sent DM to user {user_id}.")
    except Exception as e:
        logger.error(f"Error sending DM to user {user_id}: {e}", exc_info=True)


@app.command("/summarize")
def handle_summarize(ack, body, client, respond):
    """
    Slash command handler for /summarize.
    Fetches channel messages (and threaded replies) from the past 7 days,
    generates a summary, and sends the summary to the user via DM.
    """
    ack()  # Acknowledge the slash command
    logger.info(
        f"Received /summarize command from user {body['user_id']} in channel {body['channel_id']}."
    )

    user_id = body["user_id"]
    channel_id = body["channel_id"]

    # Fetch and process messages (including threads)
    messages = fetch_channel_history_with_threads(client, channel_id)
    if not messages:
        respond("No messages found in the past 7 days or an error occurred.")
        logger.warning(f"No messages to summarize in channel {channel_id}.")
        return

    # Build a single string of all messages
    conversation_text_lines = []
    for msg in messages:
        # Format: (YYYY-MM-DD HH:MM:SS) DisplayName: message text
        line = f"({msg['timestamp']}) {msg['user']}: {msg['text']}"
        conversation_text_lines.append(line)

    conversation_text = "\n".join(conversation_text_lines)

    if not conversation_text:
        respond("No text-based messages found to summarize.")
        logger.warning(f"No text messages found in channel {channel_id}.")
        return

    # Create OpenAI client and generate summary
    try:
        openai_client = OpenAI(api_key=CENTML_API_KEY,
                               base_url="https://api.centml.com/openai/v1")
        logger.info(
            "Sending conversation text to CentML OpenAI for summarization.")

        # Prepare the request payload
        request_payload = {
            "model":
            "meta-llama/Llama-3.3-70B-Instruct",
            "messages": [{
                "role":
                "system",
                "content":
                f"Please provide a concise summary of these Slack channel messages (including any threaded replies). Ignore any empty messages:\n\n{conversation_text}"
            }],
            "max_tokens":
            2000,
            "temperature":
            0.7
        }

        # Log the API request
        logger.info("POST Request to CentML OpenAI API:")
        logger.info("URL: https://api.centml.com/openai/v1/chat/completions")
        logger.info("Headers: Authorization: Bearer sk-... (truncated)")
        logger.info(
            f"Request Payload: {json.dumps(request_payload, indent=2)}")

        response = openai_client.chat.completions.create(**request_payload)

        summary = response.choices[0].message.content
        logger.info("Successfully generated summary.")
    except Exception as e:
        error_message = f"Sorry, I was unable to summarize the conversation. Error: {e}"
        send_dm_to_user(client, user_id, error_message)
        respond(
            "An error occurred while generating the summary. Check your DM for details."
        )
        logger.error("Error during summary generation.", exc_info=True)
        return

    # Send summary via DM
    send_dm_to_user(client, user_id, summary)
    respond(
        f"I've sent a summary of the last 7 days (including threaded replies) to <@{user_id}> via DM."
    )
    logger.info("Summary DM sent and command handling completed.")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Route for handling incoming Slack events.
    Logs the incoming request data before processing.
    """
    # Log the request data
    logger.info("Received Slack event:")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Data: {request.get_data().decode('utf-8')}")

    return handler.handle(request)


@flask_app.route("/install", methods=["GET"])
def install():
    """
    Route for installation landing page.
    """
    return "Add to Slack button here"


@flask_app.route("/oauth_redirect", methods=["GET"])
def oauth_redirect():
    """
    Route for handling the OAuth redirect flow.
    """
    return "OAuth flow completed"


if __name__ == "__main__":
    # Start the Flask server
    flask_app.run(host="0.0.0.0", port=3000)
