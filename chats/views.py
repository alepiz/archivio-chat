from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from . import search
from .models import Attachment, Category, Conversation, Project

PAGE_SIZE = 100


def _sidebar():
    counts = dict(
        Conversation.objects.filter(archived=False).values_list("category")
        .annotate(n=Count("id")).values_list("category", "n")
    )
    areas = []
    for area in Category.objects.filter(parent__isnull=True).prefetch_related("children"):
        children = [(c, counts.get(c.id, 0)) for c in area.children.all()]
        total = counts.get(area.id, 0) + sum(n for _, n in children)
        areas.append({"cat": area, "own": counts.get(area.id, 0), "total": total, "children": children})
    return {
        "areas": areas,
        "unassigned": counts.get(None, 0),
        "archived_count": Conversation.objects.filter(archived=True).count(),
        "all_count": sum(counts.values()),
        "all_categories": Category.objects.select_related("parent").order_by(
            "parent__order", "parent__name", "order", "name"),
    }


def _filtered(params):
    """Applica i filtri della lista. Restituisce (queryset, snippet per id, ordina per rilevanza)."""
    qs = Conversation.objects.select_related("category__parent", "project")
    qs = qs.filter(archived=params.get("vista") == "archiviate")
    cat = params.get("cat", "")
    if cat == "none":
        qs = qs.filter(category__isnull=True)
    elif cat.isdigit():
        c = Category.objects.filter(pk=int(cat)).first()
        if c:
            qs = qs.filter(category_id__in=c.descendant_ids())
    if params.get("progetto", "").isdigit():
        qs = qs.filter(project_id=int(params["progetto"]))
    if params.get("anno", "").isdigit():
        qs = qs.filter(updated_at__year=int(params["anno"]))
    if params.get("assegnata") in {"auto", "project", "manual"}:
        qs = qs.filter(assigned_by=params["assegnata"])

    snippets, by_rank = {}, None
    q = params.get("q", "").strip()
    if q:
        hits = search.search(q)
        snippets = {cid: snip for cid, snip in hits}
        by_rank = [cid for cid, _ in hits]
        qs = qs.filter(id__in=by_rank)
    return qs, snippets, by_rank


def _snippet_html(raw):
    if not raw:
        return ""
    html = escape(raw).replace("\u0001", "<mark>").replace("\u0002", "</mark>")
    return mark_safe(html)


def index(request):
    params = request.GET
    qs, snippets, by_rank = _filtered(params)
    order = params.get("ordine", "rilevanza" if by_rank is not None else "recenti")

    if order == "rilevanza" and by_rank is not None:
        rank = {cid: i for i, cid in enumerate(by_rank)}
        ids = sorted(qs.values_list("id", flat=True), key=lambda i: rank.get(i, 1e9))
        paginator = Paginator(ids, PAGE_SIZE)
        page = paginator.get_page(params.get("pagina"))
        objs = {c.id: c for c in qs.filter(id__in=list(page.object_list))}
        rows = [objs[i] for i in page.object_list if i in objs]
    else:
        ordering = {"recenti": "-updated_at", "vecchie": "updated_at", "titolo": "title",
                    "lunghe": "-message_count"}.get(order, "-updated_at")
        paginator = Paginator(qs.order_by(ordering), PAGE_SIZE)
        page = paginator.get_page(params.get("pagina"))
        rows = list(page.object_list)

    for r in rows:
        r.snippet = _snippet_html(snippets.get(r.id, ""))

    keep = {k: v for k, v in params.items() if k != "pagina" and v}
    current_cat = None
    if params.get("cat", "").isdigit():
        current_cat = Category.objects.filter(pk=int(params["cat"])).first()

    years = sorted({d.year for d in Conversation.objects.dates("updated_at", "year")}, reverse=True)
    ctx = {
        **_sidebar(),
        "rows": rows,
        "page": page,
        "total": paginator.count,
        "params": params,
        "qs_keep": urlencode(keep),
        "current_cat": current_cat,
        "cat_param": params.get("cat", ""),
        "order": order,
        "has_query": by_rank is not None,
        "filtered": any(params.get(k) for k in ("q", "cat", "anno", "progetto", "assegnata", "vista")),
        "archive_view": params.get("vista") == "archiviate",
        "years": years,
        "projects": Project.objects.annotate(n=Count("conversations")).order_by("name"),
        "next_url": request.get_full_path(),
    }
    return render(request, "chats/index.html", ctx)


def _local_path(url):
    """Accetta solo percorsi interni (es. /?cat=3), mai URL esterni o javascript:."""
    return url if url.startswith("/") and not url.startswith("//") else ""


def detail(request, pk):
    conv = get_object_or_404(
        Conversation.objects.select_related("category__parent", "project"), pk=pk)
    ctx = {
        **_sidebar(),
        "conv": conv,
        "msgs": conv.messages.all(),
        "attachments": conv.attachments.all(),
        "next_url": request.get_full_path(),
        "back_url": _local_path(request.GET.get("da", "")),
    }
    return render(request, "chats/detail.html", ctx)


def _safe_next(request, fallback="chats:index"):
    nxt = request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(fallback)


def _target_category(request):
    """Categoria scelta nel modulo: id esistente, 'nuova' + nome, o '' (nessuna)."""
    value = request.POST.get("categoria", "")
    if value == "nuova":
        name = request.POST.get("nuova_nome", "").strip()
        if not name:
            return False, None
        parent = None
        if request.POST.get("nuova_area", "").isdigit():
            parent = Category.objects.filter(pk=int(request.POST["nuova_area"]), parent__isnull=True).first()
        cat, _ = Category.objects.get_or_create(parent=parent, name=name)
        return True, cat
    if value == "none":
        return True, None
    if value.isdigit():
        cat = Category.objects.filter(pk=int(value)).first()
        return (cat is not None), cat
    return False, None


ARCHIVE_ACTIONS = {"archivia": True, "ripristina": False}


def _set_archived(ids, archived):
    return Conversation.objects.filter(id__in=ids).update(archived=archived)


@require_POST
def move(request):
    action = request.POST.get("azione", "sposta")
    cat = None
    if action not in ARCHIVE_ACTIONS:
        ok, cat = _target_category(request)
        if not ok:
            messages.error(request, "Scegli una categoria (o scrivi il nome di quella nuova).")
            return _safe_next(request)
    if request.POST.get("tutti") == "1":
        from django.http import QueryDict
        qs, _, _ = _filtered(QueryDict(request.POST.get("filtro", "")))
        ids = list(qs.values_list("id", flat=True))
    else:
        ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    if not ids:
        messages.error(request, "Nessuna chat selezionata.")
        return _safe_next(request)
    if action in ARCHIVE_ACTIONS:
        n = _set_archived(ids, ARCHIVE_ACTIONS[action])
        messages.success(request, f"{n} chat {'archiviate' if ARCHIVE_ACTIONS[action] else 'ripristinate'}.")
        return _safe_next(request)
    with transaction.atomic():
        n = Conversation.objects.filter(id__in=ids).update(
            category=cat, assigned_by="manual" if cat else "")
    dest = str(cat) if cat else "“senza categoria”"
    messages.success(request, f"{n} chat spostate in {dest}.")
    return _safe_next(request)


@require_POST
def move_one(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    action = request.POST.get("azione", "sposta")
    if action in ARCHIVE_ACTIONS:
        _set_archived([conv.id], ARCHIVE_ACTIONS[action])
        messages.success(request, "Chat archiviata." if ARCHIVE_ACTIONS[action] else "Chat ripristinata.")
        return _safe_next(request)
    ok, cat = _target_category(request)
    if not ok:
        messages.error(request, "Scegli una categoria.")
    else:
        conv.category = cat
        conv.assigned_by = "manual" if cat else ""
        conv.save(update_fields=["category", "assigned_by"])
        messages.success(request, f"Spostata in {cat if cat else '“senza categoria”'}.")
    return _safe_next(request)


def attachment(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    root = Path(settings.EXPORT_CHATGPT).resolve()
    path = (root / att.path).resolve()
    if root not in path.parents or not path.is_file():
        raise Http404("File non trovato")
    return FileResponse(open(path, "rb"), filename=att.name, as_attachment=not att.is_image)


# ------------------------------------------------------------- categorie


def categories(request):
    if request.method == "POST":
        action = request.POST.get("azione")
        try:
            _category_action(request, action)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("chats:categories")
    ctx = {
        **_sidebar(),
        "projects": Project.objects.select_related("default_category__parent").annotate(
            n=Count("conversations")).order_by("name"),
        "stats": Conversation.objects.values("assigned_by").annotate(n=Count("id")).order_by(),
    }
    return render(request, "chats/categories.html", ctx)


def _category_action(request, action):
    P = request.POST
    if action == "crea":
        name = P.get("nome", "").strip()
        if not name:
            raise ValueError("Il nome è obbligatorio.")
        parent = Category.objects.filter(pk=P.get("area") or 0, parent__isnull=True).first()
        _, created = Category.objects.get_or_create(parent=parent, name=name)
        messages.success(request, f"Categoria “{name}” {'creata' if created else 'già esistente'}.")
    elif action == "modifica":
        cat = get_object_or_404(Category, pk=P.get("id"))
        name = P.get("nome", "").strip()
        if not name:
            raise ValueError("Il nome è obbligatorio.")
        new_parent = Category.objects.filter(pk=P.get("area") or 0, parent__isnull=True).first()
        if new_parent and (new_parent.id == cat.id or cat.children.exists()):
            new_parent = cat.parent  # un'area con sottocategorie resta area
        cat.name, cat.parent = name, new_parent
        cat.keywords = P.get("parole", "")
        cat.order = int(P.get("ordine") or 0)
        cat.save()
        messages.success(request, f"Categoria “{cat}” aggiornata.")
    elif action == "elimina":
        cat = get_object_or_404(Category, pk=P.get("id"))
        ids = cat.descendant_ids()
        n = Conversation.objects.filter(category_id__in=ids).update(category=None, assigned_by="")
        label = str(cat)
        cat.delete()
        messages.success(request, f"Categoria “{label}” eliminata; {n} chat tornate senza categoria.")
    elif action == "progetto":
        proj = get_object_or_404(Project, pk=P.get("id"))
        proj.name = P.get("nome", "").strip() or proj.name
        proj.default_category = Category.objects.filter(pk=P.get("categoria") or 0).first()
        proj.save()
        n = 0
        if proj.default_category and P.get("applica"):
            n = proj.conversations.exclude(assigned_by="manual").update(
                category=proj.default_category, assigned_by="project")
        messages.success(request, f"Progetto “{proj.name}” aggiornato" + (f"; {n} chat assegnate." if n else "."))
    elif action == "classifica":
        from .classify import classify_by_keywords
        n = classify_by_keywords(overwrite_auto=bool(P.get("rifai")))
        messages.success(request, f"Classificazione per parole chiave: {n} chat assegnate.")
    else:
        raise ValueError("Azione sconosciuta.")
