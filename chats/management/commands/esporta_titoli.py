import sys

from django.core.management.base import BaseCommand

from chats.classify import export_titles


class Command(BaseCommand):
    help = "Esporta in CSV titoli ed estratti delle chat (per la classificazione assistita)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default="", help="file di uscita (predefinito: schermo)")
        parser.add_argument("--solo-senza-categoria", action="store_true")

    def handle(self, *args, **opts):
        if opts["file"]:
            with open(opts["file"], "w", encoding="utf-8", newline="") as fh:
                n = export_titles(fh, opts["solo_senza_categoria"])
            self.stderr.write(f"{n} chat esportate in {opts['file']}")
        else:
            export_titles(sys.stdout, opts["solo_senza_categoria"])
