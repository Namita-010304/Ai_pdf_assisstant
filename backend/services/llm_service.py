import os
from google.genai import types
from services.vector_store import get_genai_client

class GeminiProvider:
    """Gemini-specific provider for text generation."""

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        history: list[types.Content] | None = None,
        api_key: str | None = None,
    ) -> str:
        gc = get_genai_client(api_key)
        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction

        contents = []
        if history:
            contents.extend(history)

        # Add current user prompt
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )
        )

        response = gc.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )
        return response.text.strip() if response.text else ""


class LLMService:
    """High-level LLM Service to act as entry point for the application logic."""

    def __init__(self, provider=None):
        self.provider = provider or GeminiProvider()

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        history: list[types.Content] | None = None,
        api_key: str | None = None,
    ) -> str:
        return self.provider.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            history=history,
            api_key=api_key
        )

    def translate(self, text: str, target_lang: str, api_key: str | None = None) -> str:
        target = "Hindi" if target_lang == "hi" else "English"
        prompt = (
            f"Translate the following text into {target}. Return ONLY the translation, "
            f"without any introduction, explanations, quotes, or prefaces. Keep the meaning "
            f"and context identical:\n\n{text}"
        )
        return self.generate(prompt=prompt, api_key=api_key)
