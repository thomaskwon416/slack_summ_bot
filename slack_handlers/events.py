from flask import request
from configs.config import logger


def register_event_routes(flask_app, handler):
    """
    Registers routes/endpoints for Slack event handling.
    """

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
