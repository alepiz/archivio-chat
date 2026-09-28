"""Test con un export sintetico nel formato di ChatGPT/scrapemychats."""

import io
import json
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from . import search
from .chatgpt_format import clean_text, extract_messages
from .classify import classify_by_keywords, export_titles, import_assignments
from .importer import import_export
from .models import Category, Conversation, Project

CID1 = "68796bef-cfb0-8009-a59f-f10f2bb6f3c0"
CID2 = "6a92ee50-49b4-83eb-aadd-ac8b5204b2f0"
CID3 = "11111111-2222-3333-4444-555555555555"
PID = "g-p-6a1b2c3d4e5f60718293a4b5c6d7e8f9"


def node(nid, parent, role, content, recipient="all", meta=None, t=1700000000):
    return nid, {"id": nid, "parent": parent, "message": {
        "id": nid, "author": {"role": role, "name": None}, "create_time": t,
        "content": content, "recipient": recipient, "metadata": meta or {}}}


def conversation(cid, title, nodes, current, extra=None):
    mapping = {"root": {"id": "root", "parent": None, "message": None}}
    mapping.update(dict(nodes))
    data = {"conversation_id": cid, "title": title, "create_time": 1700000000,
            "update_time": 1700003600, "mapping": mapping, "current_node": current,
            "default_model_slug": "gpt-5"}
    data.update(extra or {})
    return data


def build_export(root):
    exp = root / "export"
    exp.mkdir()
    # 1) chat semplice con ramo alternativo (modifica), citazioni e recap
    c1 = conversation(CID1, "Quali cuffie prendere per iPod Classic", [
        node("s", "root", "system", {"content_type": "text", "parts": [""]}),
        node("u1", "s", "user", {"content_type": "text", "parts": ["Che cuffie per iPod <b>classic</b>?"]}),
        node("old", "u1", "assistant", {"content_type": "text", "parts": ["RISPOSTA SCARTATA"]}),
        node("r", "u1", "assistant", {"content_type": "reasoning_recap", "content": "Ragionato per 12s"}),
        node("th", "r", "assistant", {"content_type": "thoughts", "thoughts": [
            {"summary": "Confronto", "content": "Valuto AirPods e Sennheiser"}]}),
        node("q", "th", "assistant", {"content_type": "code", "language": "json", "text": "{\"q\":\"x\"}"},
             recipient="web.run"),
        node("a1", "q", "assistant", {"content_type": "text", "parts": [
            "Ti consiglio le **Sennheiser HD 600** citeturn0search0 "
            "e il DAP di entity[\"company\",\"FiiO\",\"produttore\"]."]}),
    ], current="a1")
    # 2) chat di progetto con codice, output e allegati
    c2 = conversation(CID2, "Aprire backup SQL Server Docker", [
        node("u1", "root", "user", {"content_type": "text", "parts": ["Come apro il backup .bak del gestionale?"]},
             meta={"attachments": [{"id": "file_1", "name": "log.txt"}]}),
        node("c", "u1", "assistant", {"content_type": "code", "language": "python", "text": "print('ciao')"},
             recipient="all"),
        node("o", "c", "tool", {"content_type": "execution_output", "text": "ciao"}),
        node("a1", "o", "assistant", {"content_type": "text", "parts": [
            "Il container è **Up** fileciteturn0file0L265-L275 sulla porta 1433."]}),
    ], current="a1", extra={"gizmo_id": PID})
    # 3) chat personale sulla finanza
    c3 = conversation(CID3, "Mutuo casa: tasso fisso o variabile", [
        node("u1", "root", "user", {"content_type": "text", "parts": ["Meglio tasso fisso o variabile per il mutuo?"]}),
        node("a1", "u1", "assistant", {"content_type": "text", "parts": ["Dipende dall'orizzonte."]}),
    ], current="a1")
    for i, (data, cid) in enumerate([(c1, CID1), (c2, CID2), (c3, CID3)], 1):
        f = exp / f"{i:03d}_{data['title'][:30]}_{cid[:8]}"
        f.mkdir()
        (f / "conversation.json").write_text(json.dumps(data), encoding="utf-8")
        (f / "conversation.md").write_text(f"# {data['title']}\n\n- URL: https://chatgpt.com/c/{cid}\n",
                                           encoding="utf-8")
    files = next(exp.glob("002_*")) / "files"
    files.mkdir()
    (files / "log.txt").write_text("contenuto log", encoding="utf-8")
    (files / "schema.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "chats.csv").write_text(
        f"url,title\nhttps://chatgpt.com/c/{CID1},a\nhttps://chatgpt.com/g/{PID}-villa/c/{CID2},b\n",
        encoding="utf-8")
    return exp


class FormatTests(TestCase):
    def test_markdown_links(self):
        from .templatetags.archivio import markdown
        html = markdown("vedi [sito](https://example.com) e [x](javascript:alert(1))")
        self.assertIn('href="https://example.com" target="_blank" rel="noopener noreferrer"', html)
        self.assertNotIn('href="javascript', html)   # resta testo, non link

    def test_clean_text(self):
        self.assertEqual(clean_text("A citeturn0search0B"), "A B")
        self.assertEqual(clean_text("x entity[\"a\",\"Nome\"]"), "x Nome")
        self.assertEqual(clean_text("porta fileciteturn0file0L1-L2."), "porta .")

    def test_active_branch_and_hidden(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            exp = build_export(tmp)
            data = json.loads(next(exp.glob("001_*")).joinpath("conversation.json").read_text())
            msgs = extract_messages(data)
            texts = " ".join(m["text"] for m in msgs)
            self.assertNotIn("RISPOSTA SCARTATA", texts)      # ramo non attivo
            self.assertNotIn('{"q":"x"}', texts)              # chiamata interna allo strumento
            self.assertEqual([m["kind"] for m in msgs], ["text", "recap", "thoughts", "text"])
            self.assertIn("FiiO", msgs[-1]["text"])
            self.assertNotIn("", texts)
        finally:
            shutil.rmtree(tmp)


class ArchiveTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.exp = build_export(self.tmp)
        self.override = override_settings(EXPORT_CHATGPT=self.exp, DATA_DIR=self.tmp)
        self.override.enable()
        self.counts, self.errors = import_export(self.exp)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp)

    def test_import_and_idempotence(self):
        self.assertEqual(self.counts["new"], 3)
        self.assertEqual(self.errors, [])
        c2 = Conversation.objects.get(external_id=CID2)
        self.assertEqual(c2.project.external_id, PID)
        self.assertEqual(c2.attachment_count, 2)
        self.assertIn("/g/g-p-", c2.url)
        counts, _ = import_export(self.exp)
        self.assertEqual(counts["skipped"], 3)
        self.assertEqual(Conversation.objects.count(), 3)
        counts, _ = import_export(self.exp, force=True)
        self.assertEqual(counts["updated"], 3)
        self.assertEqual(Conversation.objects.get(external_id=CID2).messages.count(), 4)

    def test_search(self):
        self.assertTrue(search.fts_available())
        ids = [cid for cid, _ in search.search("sennheiser")]
        self.assertEqual(ids, [Conversation.objects.get(external_id=CID1).id])
        self.assertTrue(search.search("sennh"))                 # prefisso
        self.assertTrue(search.search('"tasso fisso"'))          # frase esatta
        self.assertFalse(search.search('"fisso tasso"'))
        self.assertTrue(search.search("porta 1433"))
        self.assertEqual(search.search('"* ( ) :'), [])          # solo simboli: nessun errore
        search.search('" OR NEAR( * AND')                          # operatori FTS: nessun errore

    def test_keywords_and_manual_priority(self):
        villa = Category.objects.get(name="Villa Franciacorta")
        villa.keywords = "gestionale\nbackup"
        villa.save()
        fin = Category.objects.get(name="Finanza personale")
        fin.keywords = "mutuo"
        fin.save()
        self.assertEqual(classify_by_keywords(), 2)
        self.assertEqual(Conversation.objects.get(external_id=CID3).category, fin)
        # spostamento manuale: non viene più toccato
        c3 = Conversation.objects.get(external_id=CID3)
        resp = self.client.post(reverse("chats:move"), {"ids": [c3.id], "categoria": villa.id, "next": "/"})
        self.assertEqual(resp.status_code, 302)
        c3.refresh_from_db()
        self.assertEqual((c3.category, c3.assigned_by), (villa, "manual"))
        classify_by_keywords(overwrite_auto=True)
        c3.refresh_from_db()
        self.assertEqual(c3.category, villa)
        n = import_assignments(io.StringIO(json.dumps([{"id": CID3, "categoria": "Personale > Viaggi"}])))
        self.assertEqual(n, (0, 1, 0))

    def test_assignments_file_creates_categories(self):
        done, skipped, missing = import_assignments(io.StringIO(json.dumps({"assegnazioni": [
            {"id": CID1, "categoria": "Personale › Tecnologia personale"},
            {"id": "inesistente", "categoria": "X"}]})))
        self.assertEqual((done, skipped, missing), (1, 0, 1))
        c1 = Conversation.objects.get(external_id=CID1)
        self.assertEqual(str(c1.category), "Personale › Tecnologia personale")
        buf = io.StringIO()
        self.assertEqual(export_titles(buf), 3)
        self.assertIn("Mutuo casa", buf.getvalue())

    def test_pages(self):
        c1 = Conversation.objects.get(external_id=CID1)
        c2 = Conversation.objects.get(external_id=CID2)
        r = self.client.get(reverse("chats:index"))
        self.assertContains(r, "Quali cuffie prendere")
        r = self.client.get(reverse("chats:index"), {"q": "sennheiser"})
        self.assertContains(r, "<mark>")
        self.assertNotContains(r, "Mutuo casa")
        r = self.client.get(reverse("chats:detail", args=[c1.id]), {"da": "javascript:alert(1)"})
        self.assertNotContains(r, "javascript:alert")
        self.assertContains(r, "&lt;b&gt;classic&lt;/b&gt;")    # HTML delle chat non eseguito
        self.assertContains(r, "<strong>Sennheiser HD 600</strong>")
        self.assertContains(r, "Ragionato per 12s")
        self.assertNotContains(r, "RISPOSTA SCARTATA")
        r = self.client.get(reverse("chats:detail", args=[c2.id]))
        self.assertContains(r, "log.txt")
        att = c2.attachments.get(name="log.txt")
        r = self.client.get(reverse("chats:attachment", args=[att.id]))
        self.assertEqual(b"".join(r.streaming_content), b"contenuto log")
        self.assertEqual(self.client.get(reverse("chats:categories")).status_code, 200)

    def test_attachment_path_traversal(self):
        c2 = Conversation.objects.get(external_id=CID2)
        att = c2.attachments.first()
        att.path = "../chats.csv"
        att.save()
        self.assertEqual(self.client.get(reverse("chats:attachment", args=[att.id])).status_code, 404)

    def test_move_all_filtered_and_new_category(self):
        r = self.client.post(reverse("chats:move"), {
            "tutti": "1", "filtro": "q=mutuo", "categoria": "nuova",
            "nuova_nome": "Casa", "nuova_area": Category.objects.get(name="Personale").id, "next": "/"})
        self.assertEqual(r.status_code, 302)
        casa = Category.objects.get(name="Casa")
        self.assertEqual(list(casa.conversations.values_list("external_id", flat=True)), [CID3])

    def test_no_choice_never_unassigns(self):
        fin = Category.objects.get(name="Finanza personale")
        c3 = Conversation.objects.get(external_id=CID3)
        c3.category, c3.assigned_by = fin, "manual"
        c3.save()
        self.client.post(reverse("chats:move"), {"ids": [c3.id], "categoria": "", "next": "/"})
        c3.refresh_from_db()
        self.assertEqual(c3.category, fin)

    def test_project_default_category(self):
        proj = Project.objects.get(external_id=PID)
        villa = Category.objects.get(name="Villa Franciacorta")
        self.client.post(reverse("chats:categories"), {
            "azione": "progetto", "id": proj.id, "nome": "VILLA FRANCIACORTA",
            "categoria": villa.id, "applica": "1"})
        c2 = Conversation.objects.get(external_id=CID2)
        self.assertEqual((c2.category, c2.assigned_by), (villa, "project"))
        proj.refresh_from_db()
        self.assertEqual(proj.name, "VILLA FRANCIACORTA")

    def test_archive_and_restore(self):
        c3 = Conversation.objects.get(external_id=CID3)
        self.client.post(reverse("chats:move"), {"ids": [c3.id], "azione": "archivia", "next": "/"})
        c3.refresh_from_db()
        self.assertTrue(c3.archived)
        r = self.client.get(reverse("chats:index"))
        self.assertNotContains(r, "Mutuo casa")
        self.assertNotContains(self.client.get(reverse("chats:index"), {"q": "mutuo"}), "Mutuo casa")
        self.assertContains(self.client.get(reverse("chats:index"), {"vista": "archiviate"}), "Mutuo casa")
        import_export(self.exp, force=True)                 # la reimportazione non la ripristina
        c3.refresh_from_db()
        self.assertTrue(c3.archived)
        self.client.post(reverse("chats:move_one", args=[c3.id]), {"azione": "ripristina", "next": "/"})
        c3.refresh_from_db()
        self.assertFalse(c3.archived)

    def _fake(self, **kw):
        from . import remote_delete as rd

        class FakeSession:
            def __init__(self, gone=(), newer=(), auth_fail=False, throttle_once=(), patch_ok=True, no_time=()):
                self.gone, self.newer, self.no_time = set(gone), set(newer), set(no_time)
                self.auth_fail, self.throttle = auth_fail, set(throttle_once)
                self.patch_ok, self.deleted, self.gets = patch_ok, [], []
            def get(self, cid):
                self.gets.append(cid)
                if cid in self.throttle:
                    self.throttle.discard(cid)
                    raise rd.Throttled()
                if self.auth_fail:
                    return 401, None
                if cid in self.gone:
                    return 404, None
                if cid in self.no_time:
                    return 200, {"title": "x"}
                return 200, {"update_time": 1700003600 + (9999 if cid in self.newer else 0)}
            def delete(self, cid):
                self.deleted.append(cid)
                return 200, {"success": self.patch_ok}
        return FakeSession(**kw)

    def _run(self, session):
        from . import remote_delete as rd
        todo, _ = rd.candidates(self.exp)
        return rd.run(todo, session, self.exp, out=lambda *_: None, sleep=lambda *_: None)

    def test_remote_delete_only_archived_intact(self):
        from . import remote_delete as rd
        self.assertEqual(rd.candidates(self.exp)[0], [])            # nessuna archiviata
        Conversation.objects.update(archived=True)
        c2 = Conversation.objects.get(external_id=CID2)
        (self.exp / c2.folder / "conversation.json").write_text("{", encoding="utf-8")
        todo, rejected = rd.candidates(self.exp)
        self.assertEqual({c.external_id for c in todo}, {CID1, CID3})
        self.assertEqual([(c.external_id, w) for c, w in rejected], [(CID2, "conversation.json illeggibile")])
        fake = self._fake()
        counts = self._run(fake)
        self.assertEqual(counts["eliminate"], 2)
        self.assertEqual(sorted(fake.deleted), sorted([CID1, CID3]))
        self.assertEqual(rd.candidates(self.exp)[0], [])            # niente da rifare
        self.assertIn("eliminata", rd.log_path().read_text(encoding="utf-8"))

    def test_remote_delete_skips_chat_modified_after_backup(self):
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        fake = self._fake(newer={CID3})
        counts = self._run(fake)
        self.assertEqual((counts["eliminate"], counts["saltate"]), (0, 1))
        self.assertEqual(fake.deleted, [])
        self.assertIsNone(Conversation.objects.get(external_id=CID3).remote_deleted_at)

    def test_remote_delete_fails_closed_without_timestamps(self):
        from . import remote_delete as rd
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        fake = self._fake(no_time={CID3})
        counts = self._run(fake)
        self.assertEqual((fake.deleted, counts["saltate"]), ([], 1))
        self.assertEqual(rd.parse_time("2023-11-14T22:13:20Z"), 1700000000.0)
        self.assertEqual(rd.parse_time("1700000000.5"), 1700000000.5)
        self.assertIsNone(rd.parse_time("boh"))

    def test_remote_delete_404_not_marked_and_breaker(self):
        from . import remote_delete as rd
        Conversation.objects.update(archived=True)
        fake = self._fake(gone={CID1, CID2, CID3})
        counts = self._run(fake)
        self.assertEqual(counts["non_trovate"], 3)
        self.assertFalse(Conversation.objects.filter(remote_deleted_at__isnull=False).exists())
        # interruttore: dopo N 404 di fila si ferma
        old = rd.MAX_CONSECUTIVE_404
        rd.MAX_CONSECUTIVE_404 = 2
        try:
            fake = self._fake(gone={CID1, CID2, CID3})
            self._run(fake)
            self.assertEqual(len(fake.gets), 2)
        finally:
            rd.MAX_CONSECUTIVE_404 = old

    def test_remote_delete_stops_on_auth_loss(self):
        Conversation.objects.update(archived=True)
        fake = self._fake(auth_fail=True)
        counts = self._run(fake)
        self.assertEqual((len(fake.gets), counts["errori"], fake.deleted), (1, 1, []))

    def test_remote_delete_retries_same_chat_after_429(self):
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        fake = self._fake(throttle_once={CID3})
        counts = self._run(fake)
        self.assertEqual(fake.gets, [CID3, CID3])
        self.assertEqual(counts["eliminate"], 1)

    def test_remote_delete_rechecks_before_patch(self):
        from . import remote_delete as rd
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        todo, _ = rd.candidates(self.exp)
        Conversation.objects.filter(external_id=CID3).update(archived=False)   # ripensamento
        fake = self._fake()
        counts = rd.run(todo, fake, self.exp, out=lambda *_: None, sleep=lambda *_: None)
        self.assertEqual((fake.deleted, counts["saltate"]), ([], 1))

    def test_remote_delete_unconfirmed_patch_not_marked(self):
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        counts = self._run(self._fake(patch_ok=False))
        self.assertEqual(counts["errori"], 1)
        self.assertIsNone(Conversation.objects.get(external_id=CID3).remote_deleted_at)

    def test_remote_delete_dry_run_command(self):
        from django.core.management import call_command
        Conversation.objects.filter(external_id=CID3).update(archived=True)
        out = io.StringIO()
        call_command("elimina_su_chatgpt", stdout=out)
        self.assertIn("PROVA A VUOTO", out.getvalue())
        self.assertIn("Mutuo casa", out.getvalue())
        self.assertIsNone(Conversation.objects.get(external_id=CID3).remote_deleted_at)

    def test_delete_category_unassigns(self):
        fin = Category.objects.get(name="Finanza personale")
        Conversation.objects.filter(external_id=CID3).update(category=fin, assigned_by="manual")
        self.client.post(reverse("chats:categories"), {"azione": "elimina", "id": fin.id})
        c3 = Conversation.objects.get(external_id=CID3)
        self.assertIsNone(c3.category)
