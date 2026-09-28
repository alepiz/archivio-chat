"""Classificazione delle chat.

Priorità, dalla più forte alla più debole:
  1. manuale  — scelta da te nell'interfaccia: non viene mai sovrascritta;
  2. progetto — categoria predefinita del progetto ChatGPT;
  3. auto     — parole chiave o assegnazioni importate da file.
"""

import csv
import json

from django.db import transaction

from .models import Category, Conversation

RANK = {"": 0, "auto": 1, "project": 2, "manual": 3}


def category_by_path(path, create=True):
    """'Personale › Finanza personale' (o con '>' o '/') -> Category."""
    parts = [p.strip() for p in path.replace("›", ">").replace("/", ">").split(">") if p.strip()]
    if not parts:
        return None
    parent = None
    for name in parts[:2]:
        cat = Category.objects.filter(parent=parent, name__iexact=name).first()
        if cat is None:
            if not create:
                return None
            cat = Category.objects.create(parent=parent, name=name)
        parent = cat
    return parent


def classify_by_keywords(overwrite_auto=False):
    """Assegna le chat senza categoria (o con categoria automatica, se
    overwrite_auto) in base alle parole chiave. Il titolo pesa 4 volte."""
    rules = [(c, c.keyword_list()) for c in Category.objects.all()]
    rules = [(c, kws) for c, kws in rules if kws]
    if not rules:
        return 0
    allowed = [""] + (["auto"] if overwrite_auto else [])
    changed = 0
    qs = Conversation.objects.filter(assigned_by__in=allowed).only("id", "title", "excerpt")
    with transaction.atomic():
        for conv in qs.iterator():
            title, excerpt = conv.title.lower(), conv.excerpt.lower()
            best, best_score = None, 0
            for cat, kws in rules:
                score = sum(4 * title.count(k) + excerpt.count(k) for k in kws)
                # a parità di punteggio vince la sottocategoria (più specifica)
                if score > best_score or (score == best_score and score and cat.parent_id):
                    best, best_score = cat, score
            if best:
                Conversation.objects.filter(pk=conv.pk).update(category=best, assigned_by="auto")
                changed += 1
    return changed


def export_titles(fh, only_unassigned=False):
    """CSV con id, titolo, data, progetto, categoria attuale e inizio della
    prima domanda: il materiale per la classificazione assistita."""
    w = csv.writer(fh)
    w.writerow(["id", "titolo", "data", "progetto", "categoria", "assegnata", "estratto"])
    qs = Conversation.objects.select_related("project", "category__parent").order_by("-updated_at")
    if only_unassigned:
        qs = qs.filter(category__isnull=True)
    n = 0
    for c in qs.iterator():
        w.writerow([
            c.external_id, c.title,
            c.updated_at.date().isoformat() if c.updated_at else "",
            c.project.name if c.project else "",
            str(c.category) if c.category else "",
            c.assigned_by,
            " ".join(c.excerpt.split())[:250],
        ])
        n += 1
    return n


def import_assignments(fh):
    """Legge assegnazioni in JSON [{"id": ..., "categoria": "Area > Sotto"}]
    oppure CSV con colonne id,categoria. Le chat assegnate a mano o da
    progetto restano come sono."""
    text = fh.read()
    try:
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("assegnazioni") or rows.get("assignments") or []
    except ValueError:
        rows = list(csv.DictReader(text.splitlines()))
    done = skipped = missing = 0
    with transaction.atomic():
        for row in rows:
            ext = (row.get("id") or "").strip()
            path = (row.get("categoria") or row.get("category") or "").strip()
            if not ext or not path:
                continue
            conv = Conversation.objects.filter(external_id=ext).first()
            if conv is None:
                missing += 1
                continue
            if RANK[conv.assigned_by] > RANK["auto"]:
                skipped += 1
                continue
            conv.category = category_by_path(path)
            conv.assigned_by = "auto"
            conv.save(update_fields=["category", "assigned_by"])
            done += 1
    return done, skipped, missing
