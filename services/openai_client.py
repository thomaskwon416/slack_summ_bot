from openai import OpenAI


def get_openai_client(api_key):
    """
    Returns an OpenAI client for the CentML API endpoint.
    """
    return OpenAI(api_key=api_key, base_url="https://api.centml.com/openai/v1")
