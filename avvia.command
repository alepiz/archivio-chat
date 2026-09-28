#!/bin/bash
# Avvia l'archivio chat: importa le novità dell'export e apre il browser.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then ./installa.command || exit 1; fi
source .venv/bin/activate
python manage.py migrate -v 0
python manage.py importa || echo "(import saltato: controlla la cartella export)"
PORT=8765
( sleep 2; open "http://127.0.0.1:$PORT/" ) &
echo ""
echo "Archivio aperto su http://127.0.0.1:$PORT/  —  per chiuderlo premi Ctrl+C."
python manage.py runserver 127.0.0.1:$PORT --noreload
