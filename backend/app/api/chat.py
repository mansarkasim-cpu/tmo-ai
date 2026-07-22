from fastapi import APIRouter, HTTPException, Query
import logging
from datetime import datetime
import re
import os

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatsList,
    ChatRecord,
    MemoryRequest,
    MemoryRecord,
    MemoriesList,
)
from app.services.chat_service import ask_ai
from app.services.sql_service import save_chat, execute_query, save_memory, get_memories
from app.services.pdf_service import get_document, get_summary, get_metadata, find_best_document

router = APIRouter()
logger = logging.getLogger("tmo_ai.db")


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    document_text = None
    used_doc_id: str | None = None
    memory_context = None

    # Inline command: allow users to add memories through chat messages (supports Indonesian phrases).
    try:
        msg_raw = request.message.strip()
        msg_l = msg_raw.lower()
        trigger_match = re.search(r"\b(simpan\s+ke\s+memori|simpan\s+ke\s+memory|simpan\s+ke\s+memory|simpan\s+ke\s+memori|simpan|ingatkan|ingat|save\s+memory|remember\s+that|remember)\b", msg_l, flags=re.I)
        if trigger_match:
            # remove the trigger phrase to get the content to save
            rest = re.sub(r"(?i)\b(simpan\s+ke\s+memori|simpan\s+ke\s+memory|simpan|ingatkan|ingat|save\s+memory|remember\s+that|remember)\b[:\-]?\s*", "", msg_raw).strip()
            # try to split into key/value using first separator (:,=,-)
            m = re.match(r'^(?P<key>[^:=\-]+?)\s*(?:[:=\-])\s*(?P<value>.+)$', rest)
            if m:
                key = m.group('key').strip()
                value = m.group('value').strip()
            else:
                key = None
                value = rest.strip()

            if not value:
                # nothing to save; let normal chat flow handle it
                pass
            else:
                try:
                    rowid = save_memory(key, value)
                except Exception:
                    logger.exception("Failed to save memory from chat command")
                    raise HTTPException(status_code=500, detail="Failed to save memory")

                # record the chat and return confirmation
                conf = f"Memory saved (id={rowid}): {key + ': ' if key else ''}{value}"
                try:
                    save_chat(request.message, conf, None)
                except Exception:
                    logger.exception("Failed to save chat for memory command")

                return ChatResponse(response=conf, document_id=None)
    except Exception:
        # non-fatal: fall through to normal chat handling
        pass

    # If client provided a document_id, prefer its summary (fallback to full text).
    # If no text is available but metadata exists, still pass the document_id so
    # the agent can answer metadata-only questions (e.g., page counts).
    if request.document_id:
        meta = get_metadata(request.document_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Document not found")
        document_text = get_summary(request.document_id) or get_document(request.document_id)
        used_doc_id = request.document_id
    else:
        # No document_id provided: try to auto-select a relevant document (by token overlap).
        auto_doc_id = find_best_document(request.message)
        if auto_doc_id:
            # prefer the stored summary to keep prompts small
            document_text = get_summary(auto_doc_id) or get_document(auto_doc_id)
            used_doc_id = auto_doc_id

    # Debug log: record whether document_text is present and its length
    try:
        logger.info("chat_request: document_id=%s, text_len=%s", used_doc_id, len(document_text) if document_text else 0)
    except Exception:
        pass
    try:
        # also print to stdout so uvicorn console definitely shows it
        print(f"DEBUG chat_request: document_id={used_doc_id} text_len={len(document_text) if document_text else 0}")
    except Exception:
        pass
    try:
        with open(os.path.join(os.getcwd(), "debug_chat.log"), "a", encoding="utf-8") as _f:
            _f.write(f"REQUEST document_id={used_doc_id} text_len={len(document_text) if document_text else 0}\n")
    except Exception:
        pass
    

    # load relevant memories (best-effort). If direct search yields nothing, fetch recent memories and match tokens.
    try:
        mems = get_memories(search=request.message, limit=10) or []
        if not mems:
            all_mems = get_memories(search=None, limit=200) or []
            tokens = set([t.strip().lower() for t in re.findall(r"\w+", request.message) if len(t) > 2])
            matched = []
            for m in all_mems:
                kv = ((m.get("key") or "") + " " + (m.get("value") or "")).lower()
                if any(tok in kv for tok in tokens):
                    matched.append(m)
            mems = matched[:10]

        if mems:
            parts = []
            for m in mems:
                k = m.get("key") or ""
                v = m.get("value") or ""
                parts.append(f"{k}: {v}" if k else v)
            memory_context = "\n".join(parts)
    except Exception:
        memory_context = None

    # Heuristic: if the user asks directly about the 2024 presidential winner, and we have a matching memory, return it directly.
    try:
        q_lower = request.message.lower()
        asks_pres_2024 = re.search(r"(siapa|siapakah).*presiden.*2024|presiden.*terpilih.*2024|pilpres.*2024", q_lower)
        if asks_pres_2024:
            # look for matching memory containing 'presiden' and '2024' in key or value
            candidates = mems or []
            if not candidates:
                candidates = get_memories(search=None, limit=200) or []
            for m in candidates:
                kv = ((m.get("key") or "") + " " + (m.get("value") or "")).lower()
                if "presiden" in kv and "2024" in kv:
                    winner = m.get("value")
                    answer = f"Berdasarkan memori yang tersimpan: Presiden terpilih pada Pilpres 2024 adalah {winner}."
                    # persist chat and return
                    try:
                        save_chat(request.message, answer, used_doc_id)
                    except Exception:
                        logger.exception("Failed to save chat when returning memory-based answer")
                    return ChatResponse(response=answer, document_id=used_doc_id)
    except Exception:
        # fallthrough to normal behavior
        pass

    # Generic heuristic: if user asks 'siapa X' or 'who is X' and we have memory mentioning X, return memory directly.
    try:
        q_strip = request.message.strip()
        m_person = re.match(r"^\s*(?:siapa|siapakah)\s+(?:itu\s+)?(.+?)\s*\??$", q_strip, flags=re.I)
        if not m_person:
            m_person = re.match(r"^\s*who\s+is\s+(.+?)\s*\??$", q_strip, flags=re.I)
        if m_person:
            name_query = m_person.group(1).strip().strip('"\'')
            # search memories for exact name token
            candidates = mems or []
            if not candidates:
                candidates = get_memories(search=None, limit=200) or []

            matches = []
            nq = name_query.lower()
            for m in candidates:
                kv = ((m.get("key") or "") + " " + (m.get("value") or "")).lower()
                if nq in kv:
                    matches.append(m)

            if matches:
                # build answer from matches
                parts = []
                for m in matches:
                    v = m.get("value") or ""
                    parts.append(v)
                answer = f"Berdasarkan memori yang tersimpan tentang {name_query}: " + "; ".join(parts)
                try:
                    save_chat(request.message, answer, used_doc_id)
                except Exception:
                    logger.exception("Failed to save chat when returning memory-based person answer")
                return ChatResponse(response=answer, document_id=used_doc_id)
    except Exception:
        pass

    # Call ask_ai with a resilient strategy to handle different function signatures
    try:
        # preferred: positional (message, context, document_id)
        # merge memory_context and document_text into a single context string
        now = datetime.utcnow().date().isoformat()
        mem_prefix = ""
        if memory_context:
            mem_prefix = (
                "IMPORTANT: For this response, treat the following memories as factual and override any prior knowledge. "
                "Do not mention your internal knowledge cutoff or contradict these memories.\n"
                "Memories (treat as true):\n"
                + memory_context
                + "\n\n"
            )
        doc_prefix = ("Document summary:\n" + document_text + "\n\n") if document_text else ""
        context = f"Current date: {now}\n\n" + mem_prefix + doc_prefix

        # forward optional model selection from request to the AI caller
        answer = ask_ai(request.message, context, used_doc_id, model=request.model)
    except TypeError:
        try:
            # try keywords (some versions expect keyword args)
            answer = ask_ai(message=request.message, context=context, document_id=used_doc_id)
        except TypeError:
            try:
                # fallback: message only
                answer = ask_ai(request.message)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Internal call to ask_ai failed: {e}")
    # persist chat to DB (best-effort)
    try:
        save_chat(request.message, answer, used_doc_id)
    except Exception:
        # log DB errors for debugging but keep response for client
        logger.exception("Failed to save chat to DB")
    # Debug log: record a snippet of the AI answer for inspection
    try:
        logger.info("chat_response: document_id=%s, answer_snippet=%s", used_doc_id, (answer or "")[:300])
    except Exception:
        pass
    try:
        print(f"DEBUG chat_response: document_id={used_doc_id} answer_snippet={(answer or '')[:300]}")
    except Exception:
        pass
    try:
        with open(os.path.join(os.getcwd(), "debug_chat.log"), "a", encoding="utf-8") as _f:
            _f.write(f"RESPONSE document_id={used_doc_id} answer_snippet={(answer or '')[:300]}\n")
    except Exception:
        pass

    # Append a short debug suffix to help diagnose missing-context issues (temporary)
    try:
        suffix = f"\n\n[DEBUG: document_id={used_doc_id} text_len={len(document_text) if document_text else 0}]"
        answer = (answer or "") + suffix
    except Exception:
        pass
    return ChatResponse(response=answer, document_id=used_doc_id)



@router.post("/memories", response_model=MemoryRecord)
def add_memory(payload: MemoryRequest):
    """Add a memory key/value pair."""
    try:
        rowid = save_memory(payload.key, payload.value)
    except Exception as e:
        logger.exception("Failed to save memory")
        raise HTTPException(status_code=500, detail=str(e))

    # retrieve inserted row (best-effort)
    try:
        rows, _ = execute_query("SELECT id, key, value, created_at FROM memories WHERE id = ?", params=[rowid])
        if rows:
            r = rows[0]
            # normalize created_at
            ca = r.get("created_at")
            if ca is not None and not isinstance(ca, str):
                try:
                    r["created_at"] = ca.isoformat()
                except Exception:
                    r["created_at"] = str(ca)
            return MemoryRecord(**r)
    except Exception:
        pass

    return MemoryRecord(id=rowid, key=payload.key, value=payload.value, created_at="")


@router.get("/memories", response_model=MemoriesList)
def list_memories(q: str | None = None, limit: int = Query(50, ge=1, le=500)):
    try:
        rows = get_memories(search=q, limit=limit)
    except Exception as e:
        logger.exception("Failed to load memories")
        rows = []

    items = []
    for r in rows:
        rec = dict(r)
        ca = rec.get("created_at")
        if ca is not None and not isinstance(ca, str):
            try:
                rec["created_at"] = ca.isoformat()
            except Exception:
                rec["created_at"] = str(ca)
        items.append(MemoryRecord(**rec))

    return MemoriesList(items=items, total=len(items))



@router.get("/chats", response_model=ChatsList)
def list_chats(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    """Return paginated list of stored chats, newest first."""
    offset = (page - 1) * page_size

    # total count
    try:
        total_rows, _ = execute_query("SELECT COUNT(*) as total FROM chats", params=None)
        total = int(total_rows[0].get("total", 0)) if total_rows else 0
    except Exception:
        total = 0

    # fetch page
    try:
        rows, cols = execute_query(
            "SELECT id, message, response, document_id, created_at FROM chats ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params=[page_size, offset],
        )
    except Exception:
        rows = []

    # ensure items match ChatRecord shape; normalize created_at to string
    items = []
    for r in rows:
        rec = dict(r)
        ca = rec.get("created_at")
        if ca is not None and not isinstance(ca, str):
            try:
                rec["created_at"] = ca.isoformat()
            except Exception:
                rec["created_at"] = str(ca)
        items.append(ChatRecord(**rec))

    return ChatsList(items=items, total=total, page=page, page_size=page_size)

