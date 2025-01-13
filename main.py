from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask

from configs.config import (
    SLACK_SIGNING_SECRET,
    SLACK_BOT_TOKEN,
)
from slack_handlers.commands import register_slash_commands
from slack_handlers.events import register_event_routes

# Initialize the Slack Bolt App and Flask app
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# Register slash commands
register_slash_commands(app)

# Register event routes
register_event_routes(flask_app, handler)


@flask_app.route("/install", methods=["GET"])
def install():
    return "Add to Slack button here"


@flask_app.route("/oauth_redirect", methods=["GET"])
def oauth_redirect():
    return "OAuth flow completed"


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000)
