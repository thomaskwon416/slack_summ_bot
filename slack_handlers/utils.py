import datetime
from configs.config import logger


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

        # Build user cache
        user_cache = build_user_cache(client, raw_messages)

        # 2) Iterate over top-level messages and fetch threaded replies
        all_messages = []
        for top_msg in raw_messages:
            # Add the parent (top-level) message
            all_messages.append(process_slack_message(top_msg, user_cache))

            # If there's a thread, fetch replies
            if top_msg.get("reply_count", 0) > 0:
                thread_ts = top_msg["ts"]
                try:
                    replies_resp = client.conversations_replies(
                        channel=channel_id,
                        ts=thread_ts,
                        oldest=one_week_ago_ts,
                        limit=1000)
                    thread_messages = replies_resp.get("messages", [])
                    if len(thread_messages) > 1:
                        for reply_msg in thread_messages[1:]:
                            all_messages.append(
                                process_slack_message(reply_msg, user_cache))
                except Exception as e:
                    logger.error(
                        f"Error fetching thread replies for ts={thread_ts}: {e}",
                        exc_info=True)

        # 3) Sort everything by raw Slack timestamp
        all_messages.sort(key=lambda m: float(m["raw_ts"]))
        return all_messages

    except Exception as e:
        logger.error(
            f"Error fetching channel history or threaded replies: {e}",
            exc_info=True)
        return []


def build_user_cache(client, raw_messages):
    """
    Builds a user cache { user_id: display_name } for the messages.
    """
    user_ids = {msg["user"] for msg in raw_messages if "user" in msg}
    user_cache = {}
    for uid in user_ids:
        try:
            user_info = client.users_info(user=uid)
            profile = user_info["user"]["profile"]
            display_name = profile.get("display_name") or profile.get(
                "real_name") or uid
            user_cache[uid] = display_name
        except Exception as e:
            logger.error(f"Unable to fetch display name for user {uid}: {e}",
                         exc_info=True)
            user_cache[uid] = uid  # fallback
    return user_cache


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
        "raw_ts": raw_ts,
        "text": text,
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
