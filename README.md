# Liberatorie da sondaggi WhatsApp

Un piccolo programma per preparare il riepilogo dei consensi alle foto e ai video di un'attività scolastica partendo dagli screenshot dei voti di un sondaggio WhatsApp.

Legge i nomi negli screenshot sul computer, ti fa controllare e correggere gli abbinamenti e crea due PDF distinti:

- `Liberatoria-NomeEvento-Scuola.pdf`: nomi ed esiti individuali, da inviare alla scuola;
- `Riepilogo-NomeEvento-Chat.pdf`: solo conteggi, da condividere nella chat dei genitori.

Crea anche `Messaggi-NomeEvento.txt` con testi da copiare. Non invia messaggi da solo. La firma del rappresentante è facoltativa: può inserire un'immagine PNG della propria firma oppure firmare il PDF dopo averlo generato. Il programma non raccoglie firme dei genitori e non crea una firma digitale del PDF.

## Come iniziare

1. Scarica il repository con **Code → Download ZIP** ed estrailo in una cartella locale non sincronizzata con Dropbox, OneDrive o iCloud. Il programma blocca l'avvio da una cartella cloud per evitare di sincronizzare l'elenco dei bambini e le risposte.
2. Apri [ISTRUZIONI-VELOCI.txt](ISTRUZIONI-VELOCI.txt). Scegli **uno solo** tra `01-ROSTER.xlsx`, `01-ROSTER.ods` e `01-ROSTER.md`, sostituisci tutte le righe di esempio con l'elenco ufficiale della classe e sposta gli altri due file fuori dalla cartella.
3. Avvia `Liberatoria.command` su Mac, `Liberatoria.bat` su Windows o `Liberatoria.sh` su Linux. Scegli gli screenshot del sondaggio e controlla la tabella prima di scrivere `CONFERMO`.
4. Controlla i PDF prima di inviarli. Alla chat allega solo il file che termina in `-Chat.pdf`.

La guida completa è in [LEGGIMI.txt](LEGGIMI.txt). La prima volta serve una connessione per installare ReportLab; per leggere gli screenshot serve Tesseract OCR oppure, su Mac, Vision. Le immagini vengono elaborate sul computer.

## Dati personali

I file del repository contengono soltanto **tre bambini di esempio**. Non pubblicare il tuo elenco compilato, `dati-classe.txt`, immagini della firma, screenshot, PDF o messaggi generati. I tre file di esempio del roster sono tracciati in Git: se lavori direttamente in una copia clonata, controlla sempre `git status` prima di pubblicare modifiche.
