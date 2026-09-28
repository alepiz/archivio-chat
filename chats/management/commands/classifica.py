from django.core.management.base import BaseCommand

from chats.classify import classify_by_keywords


class Command(BaseCommand):
    help = "Classifica per parole chiave le chat senza categoria."

    def add_arguments(self, parser):
        parser.add_argument("--rifai", action="store_true",
                            help="riclassifica anche le chat assegnate in automatico")

    def handle(self, *args, **opts):
        n = classify_by_keywords(overwrite_auto=opts["rifai"])
        self.stdout.write(self.style.SUCCESS(f"{n} chat classificate."))
