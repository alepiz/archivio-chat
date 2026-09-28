"""Ricerca full-text con SQLite FTS5 (una riga per conversazione).

Se FTS5 non fosse disponibile nel Python del Mac, la ricerca ripiega su
una LIKE sul titolo e sul testo dei messaggi (più lenta ma funzionante).
"""

import re

from django.db import connection

FTS_TABLE = "chats_conversation_fts"
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def fts_available():
    with connection.cursor() as c:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [FTS_TABLE])
        return c.fetchone() is not None


def create_fts(cursor=None):
    sql = (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5("
        "title, body, tokenize='unicode61 remove_diacritics 2')"
    )
    if cursor is not None:
        cursor.execute(sql)
        return True
    with connection.cursor() as c:
        c.execute(sql)
    return True


def index_conversation(conv_id, title, body):
    if not fts_available():
        return
    with connection.cursor() as c:
        c.execute(f"DELETE FROM {FTS_TABLE} WHERE rowid = %s", [conv_id])
        c.execute(f"INSERT INTO {FTS_TABLE}(rowid, title, body) VALUES (%s, %s, %s)",
                  [conv_id, title, body])


def remove_conversation(conv_id):
    if fts_available():
        with connection.cursor() as c:
            c.execute(f"DELETE FROM {FTS_TABLE} WHERE rowid = %s", [conv_id])


def build_query(text):
    """Testo libero -> query FTS5 sicura: ogni parola come prefisso, in AND.
    Le frasi tra virgolette restano frasi esatte."""
    parts = []
    for phrase in re.findall(r'"([^"]+)"', text):
        words = _TOKEN_RE.findall(phrase)
        if words:
            parts.append('"' + " ".join(words) + '"')
    rest = re.sub(r'"[^"]*"', " ", text)
    for word in _TOKEN_RE.findall(rest):
        parts.append(f'"{word}"*')
    return " AND ".join(parts)


def search(text, limit=5000):
    """Restituisce [(conversation_id, snippet_html)] per rilevanza."""
    query = build_query(text)
    if not query:
        return []
    if fts_available():
        with connection.cursor() as c:
            c.execute(
                f"SELECT rowid, snippet({FTS_TABLE}, -1, '\u0001', '\u0002', ' … ', 18) "
                f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH %s "
                f"ORDER BY bm25({FTS_TABLE}, 8.0, 1.0) LIMIT %s",
                [query, limit],
            )
            return c.fetchall()
    # ripiego senza FTS5
    from .models import Conversation
    words = _TOKEN_RE.findall(text)
    qs = Conversation.objects.all()
    for w in words:
        qs = qs.filter(models_q(w))
    return [(cid, "") for cid in qs.values_list("id", flat=True)[:limit]]


def models_q(word):
    from django.db.models import Exists, OuterRef, Q
    from .models import Message
    return Q(title__icontains=word) | Q(
        Exists(Message.objects.filter(conversation=OuterRef("pk"), text__icontains=word))
    )
