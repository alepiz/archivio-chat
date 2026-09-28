"""Importazione dell'export ChatGPT prodotto da scrapemychats.

Struttura attesa:
    <export>/NNN_Titolo_abcd1234/conversation.json
    <export>/NNN_Titolo_abcd1234/files/...
    <export>/../chats.csv            (facoltativo: URL con /g/<progetto>/c/<id>)

L'importazione è ripetibile: le chat invariate vengono saltate, quelle
cambiate vengono aggiornate, e la categoria assegnata a mano non viene mai
toccata.
"""

import csv
import json
import re
from pathlib import Path

from django.db import transaction

from . import search
from .chatgpt_format import clean_text, extract_messages, project_id, ts
from .models import Attachment, Conversation, Message, Project

CID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PROJECT_URL_RE = re.compile(r"/g/(g-p-[A-Za-z0-9]+)[^/]*/c/(" + CID_RE.pattern + ")")


def _projects_from_csv(export_dir):
    """cid -> id progetto, dalle URL di chats.csv (se presente)."""
    mapping = {}
    for candidate in (export_dir.parent / "chats.csv", export_dir / "chats.csv"):
        if candidate.exists():
            with open(candidate, encoding="utf-8-sig", newline="") as f:
                for row in csv.reader(f):
                    if row:
                        m = PROJECT_URL_RE.search(row[0])
                        if m:
                            mapping[m.group(2)] = m.group(1)
            break
    return mapping


def _conversation_id(data, folder):
    cid = data.get("conversation_id") or data.get("id") or ""
    if CID_RE.fullmatch(cid or ""):
        return cid
    md = folder / "conversation.md"
    if md.exists():
        m = CID_RE.search(md.read_text(encoding="utf-8", errors="replace")[:1000])
        if m:
            return m.group(0)
    return ""


def _get_project(pid, cache):
    if not pid:
        return None
    if pid not in cache:
        cache[pid], _ = Project.objects.get_or_create(
            external_id=pid, defaults={"name": f"Progetto {pid[-6:]}"})
    return cache[pid]


def import_folder(folder, export_dir, csv_projects, project_cache, force=False):
    """Importa una cartella. Restituisce 'new', 'updated', 'skipped' o 'error:...'."""
    jf = folder / "conversation.json"
    try:
        mtime = jf.stat().st_mtime
        data = json.loads(jf.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"error:{e}"
    cid = _conversation_id(data, folder)
    if not cid:
        return "error:id conversazione non trovato"

    conv = Conversation.objects.filter(source="chatgpt", external_id=cid).first()
    if conv and not force and conv.source_mtime == mtime:
        return "skipped"
    status = "updated" if conv else "new"

    messages = extract_messages(data)
    project = _get_project(project_id(data) or csv_projects.get(cid, ""), project_cache)
    first_user = next((m["text"] for m in messages if m["role"] == "user"), "")
    title = clean_text(data.get("title") or "") or folder.name
    url = (f"https://chatgpt.com/g/{project.external_id}/c/{cid}" if project
           else f"https://chatgpt.com/c/{cid}")

    files_dir = folder / "files"
    files = sorted(p for p in files_dir.iterdir() if p.is_file()) if files_dir.is_dir() else []

    with transaction.atomic():
        if conv is None:
            conv = Conversation(source="chatgpt", external_id=cid)
        conv.title = title[:500]
        conv.created_at = ts(data.get("create_time"))
        conv.updated_at = ts(data.get("update_time")) or conv.created_at
        conv.model_slug = (data.get("default_model_slug") or "")[:80]
        conv.url = url
        conv.folder = str(folder.relative_to(export_dir))
        conv.project = project
        conv.message_count = len(messages)
        conv.attachment_count = len(files)
        conv.excerpt = first_user[:400]
        conv.source_mtime = mtime
        if not conv.category_id and project and project.default_category_id:
            conv.category_id = project.default_category_id
            conv.assigned_by = "project"
        conv.save()

        conv.messages.all().delete()
        Message.objects.bulk_create([
            Message(conversation=conv, position=i, role=m["role"], kind=m["kind"],
                    author_name=m["author_name"][:80], language=m["language"][:40],
                    text=m["text"], created_at=m["created_at"])
            for i, m in enumerate(messages)
        ], batch_size=500)

        conv.attachments.all().delete()
        Attachment.objects.bulk_create([
            Attachment(conversation=conv, name=p.name[:300],
                       path=str(p.relative_to(export_dir)), size=p.stat().st_size)
            for p in files
        ])

        body = "\n\n".join(m["text"] for m in messages)
        search.index_conversation(conv.id, conv.title, body)
    return status


def import_export(export_dir, force=False, limit=0, progress=None):
    export_dir = Path(export_dir).expanduser().resolve()
    if not export_dir.is_dir():
        raise FileNotFoundError(f"Cartella export non trovata: {export_dir}")
    if not search.fts_available():
        search.create_fts()
    csv_projects = _projects_from_csv(export_dir)
    project_cache = {}
    folders = sorted(p for p in export_dir.iterdir()
                     if p.is_dir() and (p / "conversation.json").exists())
    if limit:
        folders = folders[:limit]
    counts = {"new": 0, "updated": 0, "skipped": 0, "error": 0}
    errors = []
    for i, folder in enumerate(folders, 1):
        result = import_folder(folder, export_dir, csv_projects, project_cache, force=force)
        if result.startswith("error:"):
            counts["error"] += 1
            errors.append(f"{folder.name}: {result[6:]}")
        else:
            counts[result] += 1
        if progress and (i % 100 == 0 or i == len(folders)):
            progress(i, len(folders), counts)
    return counts, errors
