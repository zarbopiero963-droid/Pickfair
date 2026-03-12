import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_fix(log_text):
    prompt = f"""
Analyze pytest failure log and propose minimal fix.

LOG:
{log_text}
"""

    resp = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return resp.output_text


if __name__ == "__main__":
    with open("pytest.log") as f:
        log = f.read()

    print(generate_fix(log))