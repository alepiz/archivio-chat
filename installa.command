#!/bin/bash
# Installa l'archivio chat: ambiente Python separato + database.
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Python 3 non trovato. Installalo da python.org e riprova."; exit 1
fi
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
python manage.py migrate -v 0
echo ""
echo "Installazione completata."
echo "Cartella export ChatGPT usata: $(python -c 'import django,os;os.environ.setdefault("DJANGO_SETTINGS_MODULE","archivio.settings");django.setup();from django.conf import settings;print(settings.EXPORT_CHATGPT)')"
echo "Per avviare: ./avvia.command  (oppure doppio clic nel Finder)"
