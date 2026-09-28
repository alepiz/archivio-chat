from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chats.importer import import_export


class Command(BaseCommand):
    help = "Importa (o aggiorna) l'export ChatGPT nell'archivio."

    def add_arguments(self, parser):
        parser.add_argument("cartella", nargs="?", help="cartella export (predefinita: impostazioni)")
        parser.add_argument("--forza", action="store_true", help="reimporta anche le chat invariate")
        parser.add_argument("--limite", type=int, default=0, help="importa al massimo N chat")

    def handle(self, *args, **opts):
        folder = opts["cartella"] or settings.EXPORT_CHATGPT
        self.stdout.write(f"Importo da {folder}")

        def progress(i, total, c):
            self.stdout.write(f"  {i}/{total}  nuove {c['new']}  aggiornate {c['updated']}  "
                              f"invariate {c['skipped']}  errori {c['error']}")

        try:
            counts, errors = import_export(folder, force=opts["forza"],
                                           limit=opts["limite"], progress=progress)
        except FileNotFoundError as e:
            raise CommandError(str(e))
        for e in errors[:50]:
            self.stderr.write(f"  ! {e}")
        self.stdout.write(self.style.SUCCESS(
            f"Fatto: {counts['new']} nuove, {counts['updated']} aggiornate, "
            f"{counts['skipped']} invariate, {counts['error']} errori."))
