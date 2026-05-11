from openai import OpenAI

from backend.config_store import get_openai_key, get_openai_model


class OpenAIConfigurationError(Exception):
    pass


def _client() -> OpenAI:
    api_key = get_openai_key()

    if not api_key:
        raise OpenAIConfigurationError(
            'OpenAI API key is not configured'
        )

    return OpenAI(api_key=api_key)


async def ask_ai(prompt: str):
    client = _client()

    response = client.responses.create(
        model=get_openai_model(),
        input=prompt
    )

    return response.output_text
