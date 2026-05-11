from openai import OpenAI

from backend.config_store import get_openai_key
from backend.model_router import choose_model


class OpenAIConfigurationError(Exception):
    pass


def _client() -> OpenAI:
    api_key = get_openai_key()

    if not api_key:
        raise OpenAIConfigurationError(
            'OpenAI API key is not configured'
        )

    return OpenAI(api_key=api_key)


async def ask_ai(prompt: str, task_type: str | None = None):
    client = _client()
    model = choose_model(task_type=task_type, prompt=prompt)

    response = client.responses.create(
        model=model,
        input=prompt
    )

    return {
        'model': model,
        'answer': response.output_text
    }
