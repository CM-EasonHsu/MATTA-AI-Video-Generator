from google import genai
from google.genai import types
import base64
import json


def generate_prompt_suggestions(image_bytes: str, mime_type: str) -> dict:
    client = genai.Client(
        vertexai=True,
        project="matta2024-malaysiaairlines",
        location="us-central1",
    )

    msg1_image1 = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    msg1_text1 = types.Part.from_text(
        text="""Suggest 3 creative video generation prompts based on this image, under 30 words each. The theme is Travel, and each prompt must include a specific travel destination. Be imaginative, descriptive, and fun."""
    )

    model = "gemini-2.0-flash-001"
    contents = [
        types.Content(role="user", parts=[msg1_image1, msg1_text1]),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_p=0.95,
        max_output_tokens=1024,
        response_modalities=["TEXT"],
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ],
        response_mime_type="application/json",
        response_schema={"type": "OBJECT", "properties": {"prompts": {"type": "ARRAY", "items": {"type": "STRING"}}}},
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )

    prompts = json.loads(response.text).get("prompts", [])
    return prompts
