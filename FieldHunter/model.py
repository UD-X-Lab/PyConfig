from openai import OpenAI
import os

import utils

def with_retry_on_error():
    pass

def chat_llm(prompt, output_dir, model="gpt-4o"):
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    if model == "gpt-3.5-turbo":
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    elif model == "gpt-4o":
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    else:
        raise ValueError(f"Unsupported model: {model}")

    reply = response.choices[0]
    utils.write_file(reply.message.content, output_dir)
