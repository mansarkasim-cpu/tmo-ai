import os
from typing import Any


class SimpleResponse:
    def __init__(self, content: str):
        self.content = content


class OllamaWrapper:
    def __init__(self, model: str = "qwen3:8b", temperature: float = 0.0):
        try:
            from langchain_ollama import ChatOllama

            self.client = ChatOllama(model=model, temperature=temperature)
        except Exception as e:
            raise RuntimeError("Ollama/ChatOllama not available") from e

    def invoke(self, prompt: str) -> SimpleResponse:
        r = self.client.invoke(prompt)
        # expect r has .content, but be defensive
        content = getattr(r, "content", None)
        if content is None:
            try:
                content = r[0]
            except Exception:
                content = str(r)
        return SimpleResponse(content)


class HFWrapper:
    def __init__(self, model_name: str | None = None):
        try:
            from transformers import pipeline
        except Exception as e:
            raise RuntimeError("transformers is required for HF backend. Install with: pip install transformers") from e

        model_name = model_name or os.environ.get("TMO_AI_HF_MODEL", "facebook/blenderbot-400M-distill")
        # choose conversational pipeline for BlenderBot models, fallback to text-generation
        if "blenderbot" in model_name.lower():
            self.task = "conversational"
            self.pipe = pipeline("conversational", model=model_name)
            from transformers import Conversation

            self.Conversation = Conversation
        else:
            self.task = "text-generation"
            self.pipe = pipeline("text-generation", model=model_name)

    def invoke(self, prompt: str) -> SimpleResponse:
        if self.task == "conversational":
            conv = self.Conversation(prompt)
            out = self.pipe(conv)
            # pipeline returns list like [Conversation(..., generated_responses=[...])]
            text = ""
            try:
                text = out[0].generated_responses[-1]
            except Exception:
                try:
                    text = str(out[0])
                except Exception:
                    text = ""
        else:
            out = self.pipe(prompt, max_length=512, do_sample=True, top_p=0.9, temperature=0.7)
            text = out[0].get("generated_text", "") if isinstance(out[0], dict) else str(out[0])

        return SimpleResponse(text)


def get_llm(model: str | None = None) -> Any:
    """Return an LLM-like object with method `invoke(prompt) -> {content: str}`.

    If `model` is provided it may be a prefixed value:
    - `hf:<model_name>` to force Hugging Face pipeline
    - `ollama:<model_name>` to force Ollama
    If not provided, environment variables and availability determine the backend.
    """
    force_hf = os.environ.get("TMO_AI_FORCE_HF", "").lower() in ("1", "true", "yes")

    # explicit model selection takes precedence
    if model:
        m = model.strip()
        if m.lower().startswith("hf:"):
            return HFWrapper(model_name=m[3:])
        if m.lower().startswith("ollama:"):
            return OllamaWrapper(model=m[7:])
        # heuristic: if it looks like a HF model (contains '/'), use HF
        if "/" in m or "-" in m:
            return HFWrapper(model_name=m)
        # otherwise try Ollama style if it contains ':' (ollama image tag)
        if ":" in m:
            try:
                return OllamaWrapper(model=m)
            except Exception:
                return HFWrapper(model_name=m)

    if force_hf:
        return HFWrapper()

    # try Ollama first, then HF
    try:
        model_env = os.environ.get("TMO_AI_OLLAMA_MODEL", "qwen3:8b")
        temp = float(os.environ.get("TMO_AI_TEMPERATURE", "0"))
        return OllamaWrapper(model=model_env, temperature=temp)
    except Exception:
        return HFWrapper()
