================================================================================
                         PICKFAIR v3.0
            Dutching, Cashout, Telegram Signals
================================================================================

DESCRIZIONE
-----------
Applicazione desktop per Windows che permette di calcolare e piazzare
scommesse dutching su Betfair Exchange Italia. Supporta tutti i tipi
di mercato e aggiornamento quote in tempo reale via Streaming API.


MERCATI SUPPORTATI
------------------
- Esito Finale (1X2)
- Risultato Esatto
- Over/Under 1.5, 2.5, 3.5 Goal
- Goal/No Goal (BTTS)
- Doppia Chance
- Draw No Bet
- Primo Tempo
- Risultato Primo Tempo
- Primo Tempo/Finale
- Handicap Asiatico
- Primo Marcatore
- Marcatore (Anytime)
- Totale Goal
- Pari/Dispari Goal
- Margine Vittoria
- E altri...


NUOVE FUNZIONALITA v2.0
-----------------------
[+] Supporto tutti i mercati disponibili
[+] Streaming API per quote in tempo reale
[+] Selezione mercato da dropdown
[+] Visualizzazione disponibilita quote
[+] Aggiornamento automatico calcoli durante streaming


REQUISITI
---------
1. Account Betfair Italia (registrato su betfair.it)
2. Certificato SSL per API (da richiedere su developers.betfair.com)
3. App Key Betfair (da creare su developers.betfair.com)
4. Python 3.8+ (se esegui senza compilare)


INSTALLAZIONE RAPIDA
--------------------

Metodo 1: Esegui direttamente (richiede Python)
  1. Doppio click su AVVIA.bat
  2. Attendi installazione dipendenze automatica
  3. L'applicazione si avvia

Metodo 2: Crea eseguibile .exe
  1. Doppio click su BUILD.bat
  2. Attendi 2-3 minuti
  3. Trova Pickfair.exe in dist/
  4. Copia l'exe dove vuoi ed esegui


PRIMO AVVIO
-----------
1. Avvia l'applicazione
2. Menu File > Configura Credenziali
3. Inserisci:
   - Username Betfair
   - App Key
   - Certificato SSL (file .pem o copia/incolla)
   - Chiave Privata (file .pem o copia/incolla)
4. Clicca "Salva"
5. Clicca "Connetti" nella barra superiore
6. Inserisci la password Betfair


COME USARE
----------
1. Connettiti a Betfair
2. Seleziona una partita dalla lista
3. Scegli il tipo di mercato dal dropdown
4. [Opzionale] Attiva "Streaming Quote Live" per aggiornamenti automatici
5. Clicca sulle selezioni che vuoi includere (appare X)
6. Imposta lo stake totale
7. Scegli BACK o LAY
8. I calcoli si aggiornano automaticamente
9. Se tutto OK, clicca "Piazza Scommesse"


STREAMING API
-------------
- Attiva la checkbox "Streaming Quote Live"
- Le quote si aggiornano automaticamente in tempo reale
- Il calcolo dutching si aggiorna durante lo streaming
- Disattiva per ridurre consumo banda/CPU
- Nota: lo streaming si ferma quando cambi mercato


REGOLE BETFAIR ITALIA
---------------------
- Puntata minima BACK: 2.00 EUR
- Incrementi puntata: 0.50 EUR
- Vincita massima: 10.000 EUR (stake incluso)
- Le scommesse vengono validate automaticamente


STRUTTURA FILE
--------------
python-app/
  main.py           - Applicazione principale
  betfair_client.py - Client API e Streaming
  database.py       - Database SQLite locale
  dutching.py       - Calcoli matematici
  BUILD.bat         - Crea eseguibile
  AVVIA.bat         - Avvia senza compilare
  README.txt        - Questo file


DOVE VENGONO SALVATI I DATI
---------------------------
Windows: %APPDATA%\Pickfair\betfair.db

Il file contiene:
- Credenziali salvate
- Storico scommesse


RISOLUZIONE PROBLEMI
--------------------
"Login fallito"
  - Verifica username e password
  - Controlla che certificato e chiave siano corretti
  - Assicurati che l'App Key sia attiva

"Mercato non disponibile"
  - Non tutti i mercati sono sempre aperti
  - Prova con un'altra partita
  - Alcuni mercati aprono vicino all'evento

"Errore streaming"
  - Lo streaming richiede connessione stabile
  - Prova a disattivare e riattivare
  - Usa "Aggiorna Quote" per refresh manuale

"Puntata minima non rispettata"
  - Aumenta lo stake totale
  - Con troppi risultati lo stake per singolo scende
  - Minimo 2.00 EUR per selezione BACK


SUPPORTO
--------
Per problemi con l'API Betfair:
https://developer.betfair.com/support/


DISCLAIMER
----------
Questo software e' fornito "as is" senza garanzie.
Il gioco d'azzardo puo' creare dipendenza.
Gioca responsabilmente e solo se maggiorenne.


================================================================================
                          Versione 3.0.0 - Dicembre 2024
================================================================================
