"""The generation layer: turns retrieved NeuroDB chunks into a conversational
answer. This is the one piece of this demo that isn't hand-written NeuroDB —
see docs/rag-demo.md ("Why this needs a new layer") for why that line is
drawn here and not inside neurodb-core.

Three backends behind one Protocol so swapping models is a one-line .env
change, not a rewrite: GeminiGenerator (default, Google Gemini API),
ClaudeGenerator (Anthropic Messages API), and OllamaGenerator (optional,
zero-API-cost local alternative).
"""

from __future__ import annotations

from typing import Protocol

from neurodb_client import RetrievedChunk

SYSTEM_PROMPT = (
    "You are a medical-literature search assistant. Answer the user's question using ONLY "
    "the numbered passages below, each tagged with its source book. Every sentence of your "
    "answer must end with a bracketed citation like [1] or [2] pointing at the passage(s) it "
    "came from — never state a fact without one. If the passages don't contain the answer, "
    "say so explicitly instead of guessing or using outside knowledge. This is not medical "
    "advice, and you should not present it as such."
)

CONDENSE_SYSTEM_PROMPT = (
    "Rewrite the user's latest message as a single, standalone question that makes sense "
    "without the prior chat history, so it can be used as a search query on its own. Output "
    "only the rewritten question, nothing else."
)


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no matching passages were found)"
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(f"[{i}] Source: {chunk.filename}\n{chunk.text}")
    return "\n\n".join(blocks)


class Generator(Protocol):
    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str: ...

    def condense(self, history: list[tuple[str, str]], latest_question: str) -> str: ...


class GeminiGenerator:
    """Default backend — Google Gemini API (the current `google-genai` SDK;
    the older `google-generativeai` package is deprecated upstream)."""

    def __init__(self, api_key: str, *, model: str = "gemini-flash-lite-latest"):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _generate(self, system: str, user_content: str) -> str:
        import time

        from google.genai import errors, types

        config = types.GenerateContentConfig(system_instruction=system)
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.models.generate_content(model=self._model, contents=user_content, config=config)
                return response.text or ""
            except errors.ServerError as exc:
                # Transient overload (e.g. 503 UNAVAILABLE) — worth a couple of
                # quick retries rather than failing a demo on a blip.
                last_exc = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str:
        user_content = f"Passages:\n\n{_format_context(chunks)}\n\nQuestion: {question}"
        return self._generate(SYSTEM_PROMPT, user_content)

    def condense(self, history: list[tuple[str, str]], latest_question: str) -> str:
        if not history:
            return latest_question
        transcript = "\n".join(f"{role}: {text}" for role, text in history)
        user_content = f"Chat history:\n{transcript}\n\nLatest message: {latest_question}"
        return self._generate(CONDENSE_SYSTEM_PROMPT, user_content).strip() or latest_question


class ClaudeGenerator:
    """Default backend — Anthropic Messages API."""

    def __init__(self, api_key: str, *, model: str = "claude-sonnet-5"):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str:
        user_content = f"Passages:\n\n{_format_context(chunks)}\n\nQuestion: {question}"
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def condense(self, history: list[tuple[str, str]], latest_question: str) -> str:
        if not history:
            return latest_question
        transcript = "\n".join(f"{role}: {text}" for role, text in history)
        user_content = f"Chat history:\n{transcript}\n\nLatest message: {latest_question}"
        response = self._client.messages.create(
            model=self._model,
            max_tokens=200,
            system=CONDENSE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip() or latest_question


class OllamaGenerator:
    """Optional zero-API-cost backend — a locally-hosted open model served
    by Ollama (https://ollama.com). Same interface, no cloud dependency;
    quality and reliability of `condense()` in particular will vary a lot
    more by model than the Claude backend does."""

    def __init__(self, *, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url

    def _chat(self, system: str, user_content: str) -> str:
        import requests

        res = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
            },
            timeout=120,
        )
        res.raise_for_status()
        return res.json()["message"]["content"]

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str:
        user_content = f"Passages:\n\n{_format_context(chunks)}\n\nQuestion: {question}"
        return self._chat(SYSTEM_PROMPT, user_content)

    def condense(self, history: list[tuple[str, str]], latest_question: str) -> str:
        if not history:
            return latest_question
        transcript = "\n".join(f"{role}: {text}" for role, text in history)
        user_content = f"Chat history:\n{transcript}\n\nLatest message: {latest_question}"
        return self._chat(CONDENSE_SYSTEM_PROMPT, user_content).strip() or latest_question


def build_generator(backend: str, *, api_key: str | None = None, model: str | None = None) -> Generator:
    if backend == "gemini":
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GENERATOR_BACKEND=gemini")
        return GeminiGenerator(api_key, model=model or "gemini-flash-lite-latest")
    if backend == "claude":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for GENERATOR_BACKEND=claude")
        return ClaudeGenerator(api_key, model=model or "claude-sonnet-5")
    if backend == "ollama":
        return OllamaGenerator(model=model or "llama3")
    raise ValueError(f"unknown GENERATOR_BACKEND: {backend!r} (expected 'gemini', 'claude', or 'ollama')")
