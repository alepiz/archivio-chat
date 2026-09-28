"""Eliminazione su ChatGPT delle chat archiviate nell'archivio locale.

Regole di sicurezza (tutte obbligatorie):
- si considerano solo chat ChatGPT archiviate e non ancora eliminate;
- una chat viene eliminata solo se la sua copia nel backup è integra:
  conversation.json presente, leggibile, con l'id giusto e con messaggi;
- prima di eliminare si rilegge la chat da ChatGPT: se non c'è più viene
  solo registrata come già eliminata;
- ogni esito finisce in data/eliminazioni.csv.

L'eliminazione usa la stessa richiesta del pulsante "Elimina" di ChatGPT
(PATCH /backend-api/conversation/<id> con is_visible=false).
"""

import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import Conversation

BASE_URL = "https://chatgpt.com"


# ------------------------------------------------------------------ selezione


def parse_time(value):
    """Epoch (numero o stringa numerica) o data ISO -> secondi; None se illeggibile."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def backup_update_time(conv, export_dir):
    try:
        data = json.loads((Path(export_dir) / conv.folder / "conversation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parse_time(data.get("update_time"))


def backup_problem(conv, export_dir):
    """None se il backup della chat è integro, altrimenti il motivo."""
    if not conv.folder:
        return "cartella del backup sconosciuta"
    jf = Path(export_dir) / conv.folder / "conversation.json"
    if not jf.is_file():
        return "conversation.json mancante nel backup"
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "conversation.json illeggibile"
    cid = data.get("conversation_id") or data.get("id")
    if not cid:
        return "il backup non indica l'id della chat"
    if cid != conv.external_id:
        return "il backup contiene un'altra chat"
    if not data.get("mapping"):
        return "backup senza messaggi"
    if conv.message_count == 0:
        return "nessun messaggio importato nell'archivio"
    return None


def candidates(export_dir, limit=0):
    """Restituisce (da_eliminare, scartate[(conv, motivo)])."""
    qs = Conversation.objects.filter(
        source="chatgpt", archived=True, remote_deleted_at__isnull=True,
    ).order_by("updated_at")
    ok, rejected = [], []
    for conv in qs:
        problem = backup_problem(conv, export_dir)
        if problem:
            rejected.append((conv, problem))
        else:
            ok.append(conv)
    if limit:
        ok = ok[:limit]
    return ok, rejected


# ------------------------------------------------------------------ registro


def log_path():
    return Path(settings.DATA_DIR) / "eliminazioni.csv"


def write_log(rows):
    path = log_path()
    new = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["data_ora", "id", "titolo", "esito", "dettaglio"])
        for r in rows:
            w.writerow(r)


# ------------------------------------------------------------------ esecuzione


class Throttled(Exception):
    pass


class AuthLost(Exception):
    pass


MAX_CONSECUTIVE_404 = 5
MAX_CONSECUTIVE_429 = 3


def _remote_update_time(data):
    return parse_time(data.get("update_time")) if isinstance(data, dict) else None


def run(convs, session, export_dir, pause=(2.0, 4.0), out=print, sleep=time.sleep):
    """Elimina le chat indicate usando `session` (get / delete).

    Una chat viene eliminata solo se, subito prima dell'eliminazione:
    è ancora archiviata e non eliminata, il backup è integro, e su ChatGPT
    non è stata modificata dopo il backup. Un 404 NON viene registrato come
    eliminazione (potrebbe essere il workspace sbagliato)."""
    counts = {"eliminate": 0, "non_trovate": 0, "saltate": 0, "errori": 0}
    streak_404 = streak_429 = 0

    def log(conv, esito, dettaglio=""):
        write_log([[timezone.now().isoformat(), conv.external_id, conv.title, esito, dettaglio]])

    i = 0
    while i < len(convs):
        conv = convs[i]
        label = f"[{i + 1}/{len(convs)}] {conv.title[:70]}"
        try:
            conv.refresh_from_db()
            problem = None
            if not conv.archived or conv.remote_deleted_at:
                problem = "non più archiviata o già eliminata"
            else:
                problem = backup_problem(conv, export_dir)
            if problem:
                counts["saltate"] += 1
                log(conv, "saltata", problem)
                out(f"{label}  — saltata: {problem}")
                i += 1
                continue

            status, data = session.get(conv.external_id)
            if status in (401, 403):
                raise AuthLost(f"HTTP {status}")
            if status == 404:
                streak_404 += 1
                counts["non_trovate"] += 1
                log(conv, "non_trovata", "già eliminata o workspace diverso: non registrata")
                out(f"{label}  — non trovata su ChatGPT (lasciata com'è)")
                if streak_404 >= MAX_CONSECUTIVE_404:
                    out(f"\n{MAX_CONSECUTIVE_404} chat di fila non trovate: probabilmente sei nel "
                        "workspace sbagliato. Mi fermo per sicurezza.")
                    break
                i += 1
                continue
            streak_404 = streak_429 = 0
            if status != 200:
                raise RuntimeError(f"lettura HTTP {status}")

            remote_t = _remote_update_time(data)
            backup_t = backup_update_time(conv, export_dir)
            reason = None
            if remote_t is None or backup_t is None:
                reason = "impossibile verificare l'aggiornamento"
            elif remote_t > backup_t + 1:
                reason = "modificata su ChatGPT dopo il backup (rifai l'export di questa chat)"
            if reason:                    # nel dubbio non si elimina
                counts["saltate"] += 1
                log(conv, "saltata", reason)
                out(f"{label}  — saltata: {reason}")
                i += 1
                continue

            status, data = session.delete(conv.external_id)
            if status in (401, 403):
                raise AuthLost(f"HTTP {status}")
            if status != 200 or not (isinstance(data, dict) and data.get("success") is True):
                raise RuntimeError(f"eliminazione non confermata (HTTP {status})")
            conv.remote_deleted_at = timezone.now()
            conv.save(update_fields=["remote_deleted_at"])
            log(conv, "eliminata")
            counts["eliminate"] += 1
            out(f"{label}  ✓ eliminata")
            streak_429 = 0
        except Throttled:
            streak_429 += 1
            if streak_429 >= MAX_CONSECUTIVE_429:
                out("ChatGPT continua a chiedere di rallentare: mi fermo. Rilancia più tardi.")
                break
            out("  ChatGPT chiede di rallentare: pausa di 2 minuti, poi riprovo la stessa chat...")
            sleep(120)
            continue                     # stessa chat, nessun avanzamento
        except AuthLost as e:
            log(conv, "errore", f"sessione scaduta ({e})")
            out(f"\nSessione ChatGPT scaduta o senza permessi ({e}): mi fermo. "
                "Rilancia il comando per riprendere.")
            counts["errori"] += 1
            break
        except Exception as e:  # noqa: BLE001 — si registra e si prosegue
            counts["errori"] += 1
            log(conv, "errore", str(e)[:200])
            out(f"{label}  ! errore: {e}")
        i += 1
        sleep(random.uniform(*pause))
    return counts


# ------------------------------------------------------------------ sessione ChatGPT


class ChatGPTSession:
    """Chrome reale con il tuo login ChatGPT (profilo separato in data/)."""

    def __init__(self, profile_dir, out=print):
        from playwright.sync_api import sync_playwright
        self.out = out
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir), channel="chrome", headless=False,
            no_viewport=True, chromium_sandbox=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.headers = {}

    def close(self):
        try:
            self.context.close()
        finally:
            self._pw.stop()

    def _session(self):
        """Stato del login; None se la pagina sta cambiando (login, redirect)."""
        try:
            if not self.page.url.startswith(BASE_URL):
                return None
            return self.page.evaluate(
                "() => fetch('/api/auth/session').then(r => r.json()).catch(() => null)")
        except Exception:  # noqa: BLE001 — navigazione in corso: si riprova
            return None

    def login(self):
        self.page.goto(BASE_URL, wait_until="domcontentloaded")
        state = self._session()
        if not (state and state.get("user")):
            self.out("Accedi a ChatGPT nella finestra di Chrome e passa al workspace "
                     "Business. Controllo ogni 5 secondi...")
            while not (state and state.get("user")):
                time.sleep(5)
                state = self._session()
        # intestazioni usate dall'interfaccia (token + workspace)
        with self.page.expect_response(
                lambda r: "/backend-api/conversations?" in r.url, timeout=60_000) as info:
            self.page.goto(BASE_URL, wait_until="domcontentloaded")
        req = info.value.request.headers
        self.headers = {k: v for k, v in (
            ("Authorization", req.get("authorization")),
            ("chatgpt-account-id", req.get("chatgpt-account-id")),
        ) if v}
        return state["user"].get("email", "?"), self.headers.get("chatgpt-account-id", "")

    def _fetch(self, method, path, body=None):
        res = self.page.evaluate(
            """async ({url, method, headers, body}) => {
                const opts = {method, headers: {...headers}};
                if (body !== null) { opts.headers['Content-Type'] = 'application/json';
                                     opts.body = JSON.stringify(body); }
                const r = await fetch(url, opts);
                let text = null; try { text = await r.text(); } catch (e) {}
                return {status: r.status, text};
            }""",
            {"url": BASE_URL + path, "method": method, "headers": self.headers, "body": body},
        )
        if res["status"] == 429:
            raise Throttled()
        try:
            data = json.loads(res["text"]) if res["text"] else None
        except ValueError:
            data = None
        return res["status"], data

    def workspace_ok(self):
        """Il workspace risponde ed elenca chat: condizione per iniziare."""
        for attempt in range(3):
            try:
                status, data = self._fetch("GET", "/backend-api/conversations?offset=0&limit=1")
                return status == 200 and isinstance(data, dict) and bool(data.get("items"))
            except Throttled:
                if attempt == 2:
                    raise
                self.out("ChatGPT chiede di rallentare (export in corso?): attendo 60 secondi...")
                time.sleep(60)

    def get(self, cid):
        return self._fetch("GET", f"/backend-api/conversation/{cid}")

    def delete(self, cid):
        return self._fetch("PATCH", f"/backend-api/conversation/{cid}", {"is_visible": False})


def stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")
