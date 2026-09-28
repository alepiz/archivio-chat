"""Lettura del formato conversazione di ChatGPT (backend-api/conversation/{id}).

Trasforma l'albero 'mapping' in una lista ordinata di messaggi puliti:
- segue il ramo attivo (da current_node alla radice), come fa l'interfaccia;
- salta messaggi di sistema, nascosti e chiamate interne agli strumenti;
- rimuove i marcatori di citazione (caratteri privati U+E200–U+E206) che
  nell'export appaiono come '□filecite□turn0file0□L265-L275□';
- rende leggibili i blocchi 'reasoning_recap' e 'thoughts'.
"""

import json
import re
from datetime import datetime, timezone

#  <tipo>  <argomenti>   — es. cite, filecite, entity, navlist
_MARKER_RE = re.compile(r"([a-z_]+)(.*?)", re.S)
_STRAY_RE = re.compile(r"[-]")


def _replace_marker(m):
    kind, args = m.group(1), m.group(2)
    if kind == "entity":
        # entity["tipo","Nome visibile",...] -> Nome visibile
        try:
            data = json.loads(args)
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], str):
                return data[1]
        except (ValueError, TypeError):
            pass
    return ""


def clean_text(text):
    if not text:
        return ""
    text = _MARKER_RE.sub(_replace_marker, text)
    text = _STRAY_RE.sub("", text)
    return text.strip()


def ts(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _ordered_nodes(data):
    mapping = data.get("mapping") or {}
    chain, node_id, seen = [], data.get("current_node"), set()
    while node_id and node_id not in seen:
        seen.add(node_id)
        node = mapping.get(node_id) or {}
        if node.get("message"):
            chain.append(node["message"])
        node_id = node.get("parent")
    return list(reversed(chain))


def _part_text(part):
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if "asset_pointer" in part:
            return "[immagine]"
        if part.get("content_type") == "audio_transcription":
            return part.get("text", "")
        if "text" in part:
            return part.get("text") or ""
    return ""


def extract_messages(data):
    """Restituisce [{role, kind, author_name, language, text, created_at}]."""
    out = []
    for msg in _ordered_nodes(data):
        meta = msg.get("metadata") or {}
        if meta.get("is_visually_hidden_from_conversation"):
            continue
        author = msg.get("author") or {}
        role = author.get("role", "?")
        content = msg.get("content") or {}
        ct = content.get("content_type")
        if role == "system" or ct in ("user_editable_context", "model_editable_context"):
            continue
        if msg.get("recipient") not in (None, "all"):
            continue

        kind, language = "text", ""
        if ct in ("text", "multimodal_text"):
            text = "\n\n".join(t for t in (_part_text(p) for p in content.get("parts") or []) if t)
        elif ct == "code":
            kind, language = "code", content.get("language") or ""
            text = content.get("text", "")
        elif ct == "execution_output":
            kind, text = "output", content.get("text", "")
        elif ct == "thoughts":
            kind = "thoughts"
            text = "\n\n".join(
                "**{}** {}".format(t.get("summary", "").strip(), t.get("content", "").strip()).strip()
                for t in content.get("thoughts") or []
            )
        elif ct == "reasoning_recap":
            kind, text = "recap", content.get("content") or ""
        elif ct == "tether_quote":
            kind = "quote"
            text = "{}\n\n{}".format(content.get("title", ""), content.get("text", "")).strip()
        else:
            text = content.get("text") or content.get("result") or ""
            if role == "tool":
                kind = "tool"

        text = clean_text(text)
        attachments = [a.get("name") or a.get("id") for a in meta.get("attachments") or []]
        if attachments:
            text = "\n".join(f"📎 {n}" for n in attachments) + ("\n\n" + text if text else "")
        if not text:
            continue
        out.append({
            "role": role,
            "kind": kind,
            "author_name": author.get("name") or "",
            "language": language,
            "text": text,
            "created_at": ts(msg.get("create_time")),
        })
    return out


def project_id(data):
    """ID del progetto ChatGPT (g-p-...) se la chat ne fa parte."""
    for key in ("gizmo_id", "conversation_template_id"):
        value = data.get(key) or ""
        if isinstance(value, str) and value.startswith("g-p-"):
            return value
    return ""
