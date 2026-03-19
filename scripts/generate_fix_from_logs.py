import os


def _get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai non installato. Installa 'openai' per usare generate_fix."
        ) from e

    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_fix(log_text):
    client = _get_openai_client()

    prompt = f"""
Analyze pytest failure log and propose minimal fix.

LOG:
{log_text}
"""

    resp = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return getattr(resp, "output_text", "")


if __name__ == "__main__":
    with open("pytest.log") as f:
        log = f.read()

    print(generate_fix(log))
