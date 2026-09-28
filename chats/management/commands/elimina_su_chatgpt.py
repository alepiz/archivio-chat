import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chats import remote_delete as rd


class Command(BaseCommand):
    help = ("Elimina su ChatGPT le chat archiviate nell'archivio, solo se il loro "
            "backup è integro. Senza --esegui fa solo una prova a vuoto.")

    def add_arguments(self, parser):
        parser.add_argument("--esegui", action="store_true",
                            help="elimina davvero (chiede una conferma scritta)")
        parser.add_argument("--limite", type=int, default=0,
                            help="elimina al massimo N chat in questa esecuzione")
        parser.add_argument("--profilo", default="",
                            help="cartella profilo Chrome (predefinita: data/browser_profile)")

    def handle(self, *args, **opts):
        export_dir = Path(settings.EXPORT_CHATGPT)
        todo, rejected = rd.candidates(export_dir, limit=opts["limite"])

        report = Path(settings.DATA_DIR) / f"eliminazione_elenco_{rd.stamp()}.csv"
        with open(report, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["azione", "id", "titolo", "data", "categoria", "link", "motivo"])
            for c in todo:
                w.writerow(["ELIMINA", c.external_id, c.title,
                            c.updated_at.date() if c.updated_at else "", c.category or "", c.url, ""])
            for c, why in rejected:
                w.writerow(["NON TOCCATA", c.external_id, c.title,
                            c.updated_at.date() if c.updated_at else "", c.category or "", c.url, why])

        self.stdout.write(f"Chat archiviate da eliminare su ChatGPT: {len(todo)}")
        for c in todo[:15]:
            self.stdout.write(f"  - {c.title[:80]}")
        if len(todo) > 15:
            self.stdout.write(f"  … e altre {len(todo) - 15}")
        if rejected:
            self.stdout.write(self.style.WARNING(
                f"Escluse perché il backup non è integro: {len(rejected)} (motivi nel report)"))
        self.stdout.write(f"Elenco completo: {report}")

        if not opts["esegui"]:
            self.stdout.write(self.style.SUCCESS(
                "\nPROVA A VUOTO: nessuna chat è stata eliminata. "
                "Controlla l'elenco, poi rilancia con --esegui."))
            return
        if not todo:
            self.stdout.write("Niente da eliminare.")
            return

        self.stdout.write(self.style.WARNING(
            f"\nATTENZIONE: {len(todo)} chat verranno eliminate da ChatGPT. "
            "In ChatGPT non esiste un cestino: l'operazione è definitiva.\n"
            "Le copie restano nel backup e nell'archivio."))
        expected = f"ELIMINA {len(todo)}"
        answer = input(f'Per procedere scrivi esattamente "{expected}": ').strip()
        if answer != expected:
            raise CommandError("Conferma non corrispondente: nessuna chat eliminata.")

        profile = Path(opts["profilo"] or Path(settings.DATA_DIR) / "browser_profile").expanduser()
        try:
            session = rd.ChatGPTSession(profile, out=self.stdout.write)
        except Exception as e:  # noqa: BLE001
            raise CommandError(
                f"Non riesco ad aprire Chrome ({e}). Se l'export è ancora in corso con lo "
                "stesso profilo, aspetta che finisca.")
        try:
            email, account = session.login()
            self.stdout.write(f"Collegato come {email}  (workspace {account or 'personale'})")
            if not account:
                raise CommandError("Non risulta un workspace Business attivo: passa al workspace "
                                   "Business nella finestra di Chrome e rilancia. Nessuna chat eliminata.")
            try:
                ok = session.workspace_ok()
            except rd.Throttled:
                raise CommandError("ChatGPT sta limitando le richieste (probabilmente per l'export "
                                   "in corso). Nessuna chat eliminata: riprova a export finito.")
            if not ok:
                raise CommandError("Il workspace non risponde come previsto. Nessuna chat eliminata.")
            counts = rd.run(todo, session, export_dir, out=self.stdout.write)
        finally:
            session.close()
        self.stdout.write(self.style.SUCCESS(
            f"\nFatto: {counts['eliminate']} eliminate, {counts['non_trovate']} non trovate, "
            f"{counts['saltate']} saltate, {counts['errori']} errori. Registro: {rd.log_path()}"))
        if counts["errori"]:
            self.stdout.write("Le chat con errore restano da eliminare: rilancia il comando per riprovarle.")
