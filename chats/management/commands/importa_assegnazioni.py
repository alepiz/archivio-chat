from django.core.management.base import BaseCommand

from chats.classify import import_assignments


class Command(BaseCommand):
    help = "Applica un file di assegnazioni (JSON o CSV con colonne id,categoria)."

    def add_arguments(self, parser):
        parser.add_argument("file")

    def handle(self, *args, **opts):
        with open(opts["file"], encoding="utf-8-sig") as fh:
            done, skipped, missing = import_assignments(fh)
        self.stdout.write(self.style.SUCCESS(
            f"{done} assegnate, {skipped} lasciate com'erano (manuali o da progetto), "
            f"{missing} id non trovati."))
