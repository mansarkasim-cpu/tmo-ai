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
        # log raw response for debugging (goes to stdout / journal)
        try:
            print("Ollama raw response:", r)
        except Exception:
            pass
        # expect r has .content, but be defensive
        content = getattr(r, "content", None)
        if content is None:
            try:
                content = r[0]
            except Exception:
                content = str(r)
        print("Ollama response content:", content)
        return SimpleResponse(content)


class HFWrapper:
    def __init__(self, model_name: str | None = None):
        try:
            from transformers import pipeline
            from transformers import AutoTokenizer
        except Exception as e:
            raise RuntimeError("transformers is required for HF backend. Install with: pip install transformers") from e

        model_name = model_name or os.environ.get("TMO_AI_HF_MODEL", "facebook/blenderbot-400M-distill")
        # choose conversational pipeline for BlenderBot models, fallback to text-generation
        if "blenderbot" in model_name.lower():
            self.task = "conversational"
            self.pipe = pipeline("conversational", model=model_name)
            from transformers import Conversation

            self.Conversation = Conversation
            # load tokenizer for truncation guidance
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
                self.model_max_length = getattr(self.tokenizer, "model_max_length", None) or getattr(self.tokenizer, "model_max_len", None)
            except Exception:
                self.tokenizer = None
                self.model_max_length = None
        else:
            self.task = "text-generation"
            self.pipe = pipeline("text-generation", model=model_name)
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
                self.model_max_length = getattr(self.tokenizer, "model_max_length", None) or getattr(self.tokenizer, "model_max_len", None)
            except Exception:
                self.tokenizer = None
                self.model_max_length = None

    def invoke(self, prompt: str) -> SimpleResponse:
        # if tokenizer known, ensure prompt length does not exceed model limits
        try:
            if getattr(self, "tokenizer", None) and self.model_max_length:
                try:
                    ids = self.tokenizer.encode(prompt, truncation=False)
                    if len(ids) > int(self.model_max_length):
                        # keep last portion of the prompt (most recent context)
                        keep = max(64, int(self.model_max_length) - 50)
                        trimmed_ids = ids[-keep:]
                        prompt = self.tokenizer.decode(trimmed_ids, skip_special_tokens=True)
                        print(f"Trimmed input from conversation as it was longer than {self.model_max_length} tokens.")
                        print(f"Conversation input is too long ({len(ids)}), trimming it to ({keep})")
                except Exception:
                    # tokenizer.encode may fail for some models; ignore and proceed
                    pass
        except Exception:
            pass

        if self.task == "conversational":
            conv = self.Conversation(prompt)
            out = self.pipe(conv)
            # pipeline returns list like [Conversation(..., generated_responses=[...])]
            # emit raw pipeline output for diagnostics
            try:
                print("HF pipeline raw output:", out)
            except Exception:
                pass
            text = ""
            try:
                # prefer the last generated response
                text = out[0].generated_responses[-1]
            except Exception:
                try:
                    text = str(out[0])
                except Exception:
                    text = ""
            try:
                print("HF conversational text:", text)
            except Exception:
                pass
        else:
            out = self.pipe(prompt, max_length=512, do_sample=True, top_p=0.9, temperature=0.7)
            try:
                print("HF pipeline raw output:", out)
            except Exception:
                pass
            text = out[0].get("generated_text", "") if isinstance(out[0], dict) else str(out[0])
            try:
                print("HF text-generation text:", text)
            except Exception:
                pass

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
