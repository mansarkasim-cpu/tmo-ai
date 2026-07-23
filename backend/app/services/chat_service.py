from app.services.llm_provider import get_llm
from typing import Optional
import json
import logging
import os
import time
from datetime import datetime

from app.services.kb_service import kb
from app.services.sql_service import execute_query
from app.services.pdf_service import find_best_document, get_metadata, get_summary

# Logging setup: JSONL file with one event per line
LOG_DIR = os.environ.get("TMO_AI_LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
LOG_DIR = os.path.abspath(LOG_DIR)
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "agent_events.jsonl")

logger = logging.getLogger("tmo_ai.agent")
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


def _log_event(event_type: str, payload: dict):
    entry = {"timestamp": datetime.utcnow().isoformat() + "Z", "event": event_type}
    entry.update(payload)
    try:
        logger.info(json.dumps(entry, ensure_ascii=False))
    except Exception:
        # best-effort: don't raise logging errors into agent
        pass


def _clean_response(text: str) -> str:
    """Remove common code fences and whitespace around LLM output."""
    t = text.strip()
    if t.startswith("```") and t.endswith("```"):
        # drop fences
        parts = t.split("\n", 1)
        if len(parts) > 1:
            t = parts[1].rsplit("\n```", 1)[0]
    return t.strip()


def _ask_ai_impl(message: str, context: Optional[str] = None, document_id: Optional[str] = None, max_steps: int = 6, model: Optional[str] = None) -> str:
    """A lightweight LangGraph-style agent loop driven by ChatOllama.

    Protocol: the LLM should emit a JSON object describing the action:
    {"action": "kb_search"|"sql_query"|"final", "query": "...", "k": 4}

    The agent will execute the tool and feed back the tool result as plain text
    for the next step. When LLM returns `action":"final"` with `answer`, it's returned.
    """
    system_msg = (
        "You are an intelligent assistant with access to two tools: KB_SEARCH and SQL_QUERY.\n"
        "KB_SEARCH(query, k) -> returns up to k relevant document chunks with metadata.\n"
        "SQL_QUERY(query) -> executes a readonly SQL query against the system DB and returns rows.\n"
        "When you want to use a tool, respond with a JSON object only (no surrounding text) like:\n"
        "{\"action\": \"kb_search\", \"query\": \"search terms\", \"k\": 4}\n"
        "or\n"
        "{\"action\": \"sql_query\", \"query\": \"SELECT ...\"}\n"
        "After the tool result is provided, decide to call another tool or return the final answer by replying:\n"
        "{\"action\": \"final\", \"answer\": \"Your answer here\"}\n"
        "Be concise and cite the document_id when using KB results."
    )

    user_prompt = message
    if context:
        user_prompt = "Document summary:\n" + context + "\n\nQuestion: " + message

    # prompt will be set after router and initial tool retrievals

    # instantiate per-request LLM (allows model selection)
    try:
        llm = get_llm(model)
    except Exception as e:
        _log_event("llm_error", {"error": str(e), "model": model})
        raise

    # Log the incoming query
    _log_event("query", {"message": message, "has_context": bool(context), "document_id": document_id, "model": model})

    # Quick metadata-based short-circuit: if the user asks about page count and we have document_id, answer from metadata.
    def _is_pages_question(q: str) -> bool:
        ql = q.lower()
        keywords = ["berapa halaman", "jumlah halaman", "how many pages", "pages", "berapa lembar", "jumlah lembar"]
        for k in keywords:
            if k in ql:
                return True
        # also simple pattern: 'berapa' and 'halaman' both present
        if "berapa" in ql and "halaman" in ql:
            return True
        return False

    if document_id and _is_pages_question(message):
        try:
            meta = get_metadata(document_id)
            if meta and meta.get("pages") is not None:
                pages = meta.get("pages")
                answer = f"Berdasarkan metadata dokumen, terdapat **{pages} halaman**."
                _log_event("direct_metadata_answer", {"document_id": document_id, "pages": pages})
                return answer
        except Exception as e:
            _log_event("tool_error", {"tool": "metadata_store", "error": str(e)})
    # Question Router: decide whether to use metadata, content, or both

    def _question_router(question: str) -> str:
        prompt = (
            "Decide which retrieval path is most appropriate for the user's question.\n"
            "Return a JSON object only with field 'route' whose value is one of: 'metadata', 'content', 'both'.\n"
            "- 'metadata' means the question can be answered from document metadata (filename, pages, size, existence)\n"
            "- 'content' means the question requires document content (full-text retrieval)\n"
            "- 'both' means both metadata and content may be useful.\n"
            "Question: "
            + question
        )
        try:
            r = llm.invoke(prompt)
            txt = _clean_response(r.content)
            obj = json.loads(txt)
            route = obj.get("route")
            if route in ("metadata", "content", "both"):
                return route
        except Exception:
            pass
        # fallback heuristic
        ql = question.lower()
        metadata_keywords = ["when", "where", "who", "how many", "pages", "size", "filename", "date", "id"]
        if any(k in ql for k in metadata_keywords):
            return "metadata"
        return "content"

    route = _question_router(message)
    _log_event("router_decision", {"route": route, "message": message})

    start_total = time.perf_counter()
    last_tool_result = None

    # Pre-run retrievals based on router decision and include as initial TOOL_RESULT
    initial_tool_payload = {}
    if route in ("metadata", "both"):
        try:
            doc_id = find_best_document(message)
            if doc_id:
                meta = get_metadata(doc_id) or {}
                summary = get_summary(doc_id)
                initial_tool_payload["metadata_results"] = [{"document_id": doc_id, "filename": meta.get("filename"), "pages": meta.get("pages"), "summary": summary}]
            else:
                initial_tool_payload["metadata_results"] = []
            _log_event("tool_called", {"tool": "metadata_store", "route": route, "result_count": len(initial_tool_payload.get("metadata_results", []))})
        except Exception as e:
            _log_event("tool_error", {"tool": "metadata_store", "error": str(e)})

    if route in ("content", "both"):
        try:
            results = kb.search(message, k=4)
            # build a lightweight content preview
            preview = []
            for doc, score in results[:5]:
                try:
                    meta = doc.metadata or {}
                    preview.append({"document_id": meta.get("document_id"), "chunk": meta.get("chunk"), "score": float(score)})
                except Exception:
                    preview.append({"score": float(score)})
            initial_tool_payload["content_results"] = preview
            _log_event("tool_called", {"tool": "retriever", "route": route, "result_count": len(results)})
        except Exception as e:
            _log_event("tool_error", {"tool": "retriever", "error": str(e)})

    # seed the prompt with initial tool results so the LLM can start from them
    initial_tool_text = json.dumps(initial_tool_payload, ensure_ascii=False) if initial_tool_payload else "{}"
    prompt = system_msg + "\nUser: " + user_prompt + "\n\nTOOL_RESULT: " + initial_tool_text
    for step in range(max_steps):
        resp = llm.invoke(prompt)
        text = _clean_response(resp.content)
        # try to parse JSON
        try:
            action_obj = json.loads(text)
        except Exception:
            # If the model returned plain text that looks like a direct answer
            # (and does not request a tool), accept it as a final answer.
            # Heuristic: if the text contains keywords indicating a tool request,
            # continue asking for JSON; otherwise treat as final.
            low = text.lower()
            tool_tokens = ["kb_search", "sql_query", "tool", "action", "kb", "sql", "search"]
            if any(tok in low for tok in tool_tokens):
                # ask the model to produce JSON only
                prompt = (
                    system_msg
                    + "\nUser: "
                    + user_prompt
                    + "\n\nThe previous assistant output was not valid JSON. Reply with a JSON object only describing the action.\n"
                )
                continue
            # treat as final answer
            answer = text
            total_ms = (time.perf_counter() - start_total) * 1000.0
            _log_event("final_answer", {"answer": answer, "total_time_ms": round(total_ms, 2), "note": "accepted_plain_text"})
            return answer

        action = action_obj.get("action")
        if action == "kb_search":
            q = action_obj.get("query") or action_obj.get("q")
            k = int(action_obj.get("k", 4))
            t0 = time.perf_counter()
            try:
                results = kb.search(q, k=k)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                # create a compact preview of results
                preview = []
                for r in results[:5]:
                    meta = getattr(r[0], 'metadata', r[0].metadata if hasattr(r[0], 'metadata') else None) if isinstance(r, tuple) else None
                    # r can be (_SimpleDoc or langchain Document) or tuple(doc, score)
                
                # build preview for JSON logging
                preview = []
                for doc, score in results[:5]:
                    try:
                        meta = doc.metadata or {}
                        preview.append({"document_id": meta.get("document_id"), "chunk": meta.get("chunk"), "score": float(score)})
                    except Exception:
                        preview.append({"score": float(score)})

                _log_event("tool_called", {"tool": "kb_search", "query": q, "k": k, "duration_ms": round(duration_ms, 2), "result_count": len(results), "preview": preview})
                tool_text = json.dumps({"kb_results": results}, ensure_ascii=False)
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                _log_event("tool_error", {"tool": "kb_search", "query": q, "k": k, "duration_ms": round(duration_ms, 2), "error": str(e)})
                tool_text = json.dumps({"error": str(e)})

            prompt = system_msg + "\nUser: " + user_prompt + "\n\nTOOL_RESULT: " + tool_text
            last_tool_result = tool_text
            continue

        if action == "sql_query":
            q = action_obj.get("query")
            t0 = time.perf_counter()
            try:
                rows, cols = execute_query(q, params=None, max_rows=50, readonly=True)
                duration_ms = (time.perf_counter() - t0) * 1000.0
                preview = rows[:5]
                _log_event("tool_called", {"tool": "sql_query", "query": q, "duration_ms": round(duration_ms, 2), "rows_returned": len(rows), "preview": preview})
                tool_text = json.dumps({"rows": rows, "columns": cols}, ensure_ascii=False)
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                _log_event("tool_error", {"tool": "sql_query", "query": q, "duration_ms": round(duration_ms, 2), "error": str(e)})
                tool_text = json.dumps({"error": str(e)})

            prompt = system_msg + "\nUser: " + user_prompt + "\n\nTOOL_RESULT: " + tool_text
            last_tool_result = tool_text
            continue

        if action == "final":
            answer = action_obj.get("answer") or action_obj.get("response")
            total_ms = (time.perf_counter() - start_total) * 1000.0
            if answer:
                _log_event("final_answer", {"answer": answer, "total_time_ms": round(total_ms, 2)})
                return answer
            else:
                # malformed final, continue
                prompt = (
                    system_msg
                    + "\nUser: "
                    + user_prompt
                    + "\n\nThe assistant returned a final action without an 'answer' field. Provide JSON with 'action':'final' and 'answer'.\n"
                )
                continue

        # unknown action
        prompt = (
            system_msg
            + "\nUser: "
            + user_prompt
            + "\n\nUnknown action returned: "
            + json.dumps(action_obj)
            + "\nRespond with a JSON action.\n"
        )

    # if loop ends without final answer, fallback to returning the last tool result or a generic message
    if last_tool_result:
        return "I found these results: " + last_tool_result
    return "I'm sorry, I couldn't produce an answer."


def ask_ai(*args, **kwargs):
    """Compatibility wrapper for older call patterns.

    Supports:
    - ask_ai(message)
    - ask_ai(message, context)
    - ask_ai(message, context, document_id)
    - ask_ai(message, context=..., document_id=...)
    """
    # positional mapping
    message = None
    context = None
    document_id = None
    max_steps = None

    if len(args) >= 1:
        message = args[0]
    if len(args) >= 2:
        context = args[1]
    if len(args) >= 3:
        document_id = args[2]
    if len(args) >= 4:
        max_steps = args[3]

    # override with kwargs if present
    if "message" in kwargs:
        message = kwargs.get("message")
    if "context" in kwargs:
        context = kwargs.get("context")
    if "document_id" in kwargs:
        document_id = kwargs.get("document_id")
    if "max_steps" in kwargs:
        max_steps = kwargs.get("max_steps")

    if max_steps is None:
        try:
            # record call parameters for debugging
            try:
                with open(os.path.join(os.getcwd(), "debug_chat.log"), "a", encoding="utf-8") as _f:
                    _f.write(f"ASK_AI_CALL message={message!r} context_len={len(context) if context else 0} document_id={document_id}\n")
            except Exception:
                pass
            # pass-through optional model kwarg
            model = kwargs.get("model") or args[4] if len(args) >= 5 else None
            return _ask_ai_impl(message, context=context, document_id=document_id, model=model)
        except Exception as e:
            try:
                with open(os.path.join(os.getcwd(), "debug_chat.log"), "a", encoding="utf-8") as _f:
                    _f.write(f"ASK_AI_ERROR {e}\n")
            except Exception:
                pass
            raise
    return _ask_ai_impl(message, context=context, document_id=document_id, max_steps=max_steps)