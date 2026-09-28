# Archivio chat

Archivio locale delle chat ChatGPT: lettura, ricerca full-text e
riorganizzazione in categorie. Gira solo sul Mac (http://127.0.0.1:8765),
nessun dato esce dal computer.

## Primo avvio

    cd ~/Dev/archivio-chat
    ./installa.command
    ./avvia.command

`avvia.command` importa ogni volta le chat nuove o cambiate dell'export
(quelle invariate vengono saltate in pochi secondi) e apre il browser.
Per chiudere: Ctrl+C nel Terminale.

La cartella dell'export predefinita è `~/Dev/scrapemychats/export`.
Per cambiarla crea `data/config.json`:

    {"export_chatgpt": "/percorso/della/cartella/export"}

## Organizzare le chat

- **Spostare**: seleziona le chat nell'elenco (Maiusc+clic per un
  intervallo) e scegli "Sposta in…". Dalla pagina di una chat, il menu in
  alto a destra. "+ Nuova categoria…" la crea al volo.
- **Spostare un intero risultato**: cerca (es. `mutuo`) o filtra, poi
  "Sposta tutte le N di questo elenco".
- **Categorie e progetti**: rinomina, crea, elimina categorie; dai un nome
  ai progetti ChatGPT e una categoria predefinita.
- **Priorità**: manuale > progetto > automatica. Ciò che sposti a mano non
  viene mai sovrascritto; le assegnazioni automatiche hanno l'etichetta
  bordata, quelle manuali piena. Il filtro "Automatica (da controllare)"
  mostra quelle da rivedere.

- **Archiviare**: "Archivia selezionate" (o "Archivia" nella pagina della
  chat) le toglie da elenchi, categorie e ricerche senza cancellarle.
  Si ritrovano in "Archiviate" e si ripristinano con un clic; le nuove
  importazioni non le fanno ricomparire.

## Eliminare su ChatGPT le chat archiviate

Solo dopo che l'export è finito. Le copie restano nel backup e nell'archivio.

    source .venv/bin/activate
    python manage.py elimina_su_chatgpt                      # prova a vuoto: solo elenco
    python manage.py elimina_su_chatgpt --esegui --limite 1  # prima volta: una sola chat
    python manage.py elimina_su_chatgpt --esegui             # tutte le archiviate

Si apre Chrome: accedi e passa al workspace Business. Viene chiesta la
conferma scritta "ELIMINA N". Sicurezze: solo chat archiviate con backup
integro; ricontrollo subito prima di eliminare; salta le chat modificate
su ChatGPT dopo il backup; si ferma se la sessione scade, se ChatGPT
rallenta troppo o se molte chat risultano "non trovate" (workspace
sbagliato). Registro completo in `data/eliminazioni.csv`.

## Aggiornare il programma

    cd ~/Dev && unzip -oq "$(ls -t ~/Downloads/archivio-chat*.zip | head -1)" && cd archivio-chat && ./installa.command && ./avvia.command

I dati (`data/`) non vengono toccati; gli aggiornamenti del database si
applicano da soli all'avvio.

## Classificazione assistita

    source .venv/bin/activate
    python manage.py esporta_titoli --file titoli.csv
    # ... classificazione (es. con Claude) in assegnazioni.json:
    #     [{"id": "<id chat>", "categoria": "Personale > Finanza personale"}]
    python manage.py importa_assegnazioni assegnazioni.json

Le categorie indicate nel file vengono create se mancano.

## Ricerca

Parole normali = tutte presenti (anche come inizio di parola: `siviglia`,
`contratt`). Frase esatta tra virgolette: `"tasso fisso"`.

## Dati e backup

Tutto l'archivio (categorie, spostamenti) è nel file `data/archivio.sqlite3`.
Per il backup basta copiare la cartella `data/`. Le chat e gli allegati
restano nella cartella dell'export: non cancellarla.
