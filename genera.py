#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dal sondaggio WhatsApp a due documenti: uno per la scuola e uno per la chat.

Funziona su Windows, macOS e Linux. Niente esce dal computer: nessun dato dei bambini
viene mandato da nessuna parte.

Due cose vanno preparate una volta sola, e sono spiegate in LEGGIMI.txt:
  - dati-classe.txt   la scuola, la sezione, il tuo nome. Se manca, il programma
                      te lo chiede al primo avvio e lo scrive da solo.
  - 01-ROSTER.md      l'elenco dei bambini della tua sezione, in una tabella.

I voti si possono prendere in due modi:
  - dagli screenshot del sondaggio, letti con OCR sul computer (via principale).
  - a mano: leggi il sondaggio e scrivi i numeri, solo se l'OCR non funziona.

Uso:
    python3 genera.py                          tutto interattivo
    python3 genera.py --mano                   salta gli screenshot, voti a mano
    python3 genera.py foto1.png foto2.png      screenshot gia' scelti
    python3 genera.py --evento Castagnata --data "12 novembre 2026" --mano
"""

import argparse
import csv
import datetime as dt
import difflib
import io
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

QUI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(QUI, "dati-classe.txt")

# Tutto quello che cambia da una classe all'altra sta in dati-classe.txt.
# Questi nomi vengono riempiti da carica_dati() all'avvio: non serve toccarli qui.
SCUOLA = ISTITUTO = ANNO = SEZIONE = RAPPRESENTANTE = FIGLIO = CITTA = ELEZIONE = ""
RUOLO = "madre"
ROSTER = FIRMA = ""

# chiave, domanda, esempio, obbligatorio
CAMPI = [
    ("scuola", "Nome della scuola come va scritto sui documenti",
     "Scuola dell'Infanzia Arcobaleno, Citta'", True),
    ("istituto", "Istituto comprensivo",
     'Istituto Comprensivo di Esempio', True),
    ("anno", "Anno scolastico", "2026/27", True),
    ("sezione", "Sezione", "B", True),
    ("rappresentante", "Il tuo nome e cognome", "Maria Rossi", True),
    ("ruolo", "Sei la madre o il padre? (madre / padre)", "madre", True),
    ("figlio", "Nome e cognome di tuo figlio o tua figlia", "Luca Rossi", True),
    ("elezione", "Data in cui sei stata eletta", "26 ottobre 2026", True),
    ("citta", "Citta' da scrivere sopra la firma", "Citta'", True),
    ("firma", "File PNG con la tua firma, se ce l'hai (invio per saltare)",
     "firma.png", False),
]


# ----------------------------------------------------------------------------
# dati della classe
# ----------------------------------------------------------------------------

def leggi_config(path):
    dati = {}
    if not os.path.exists(path):
        return dati
    for riga in open(path, encoding="utf-8"):
        riga = riga.strip()
        if not riga or riga.startswith("#") or ":" not in riga:
            continue
        k, v = riga.split(":", 1)
        dati[k.strip().lower()] = v.strip()
    return dati


def scrivi_config(path, dati):
    righe = ["# Dati della tua classe. Puoi correggerli quando vuoi con un editor di testo.",
             "# Una riga per voce, nella forma   chiave: valore",
             ""]
    for k, domanda, _esempio, _obb in CAMPI:
        righe.append("# %s" % domanda)
        righe.append("%s: %s" % (k, dati.get(k, "")))
        righe.append("")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(righe))


def chiedi_dati():
    print("\nPrima volta: mi servono i dati della tua classe.")
    print("Li scrivo in dati-classe.txt e non te li chiedo piu'.")
    print("Se sbagli qualcosa, apri quel file e correggilo.\n")
    dati = {}
    for k, domanda, esempio, obbligatorio in CAMPI:
        while True:
            v = input("%s\n  (esempio: %s)\n> " % (domanda, esempio)).strip()
            if v or not obbligatorio:
                break
            print("  Questo serve per forza.\n")
        dati[k] = v
        print("")
    scrivi_config(CONFIG, dati)
    print("Scritto %s\n" % os.path.basename(CONFIG))
    return dati


def carica_dati():
    global SCUOLA, ISTITUTO, ANNO, SEZIONE, RAPPRESENTANTE, FIGLIO
    global CITTA, ELEZIONE, RUOLO, ROSTER, FIRMA
    dati = leggi_config(CONFIG)
    mancanti = [k for k, _d, _e, obb in CAMPI if obb and not dati.get(k)]
    if mancanti:
        if dati:
            print("\nIn dati-classe.txt mancano: %s" % ", ".join(mancanti))
        dati = chiedi_dati()
    SCUOLA = dati["scuola"]
    ISTITUTO = dati["istituto"]
    ANNO = dati["anno"]
    SEZIONE = dati["sezione"]
    RAPPRESENTANTE = dati["rappresentante"]
    RUOLO = (dati.get("ruolo") or "madre").strip().lower()
    FIGLIO = dati["figlio"]
    ELEZIONE = dati["elezione"]
    CITTA = dati["citta"]
    firma = (dati.get("firma") or "").strip()
    if firma:
        FIRMA = firma if os.path.isabs(firma) else os.path.join(QUI, firma)
        if not os.path.exists(FIRMA):
            print("Attenzione: non trovo il file della firma (%s). "
                  "Il PDF esce con lo spazio per firmare a penna." % firma)
            FIRMA = ""


def g(femminile, maschile):
    """Sceglie la forma giusta in base al campo ruolo."""
    return femminile if RUOLO.startswith("madre") else maschile

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

STOPWORDS = {
    "mamma", "mamme", "papa", "babbo", "padre", "madre", "genitore",
    "di", "del", "della", "dei", "la", "il", "lo",
    "compagno", "compagna", "classe", "amica", "amico", "sezione", "sez",
    "dott", "dottssa", "dr", "dssa", "sig", "sigra", "prof",
}


# ----------------------------------------------------------------------------
# testo
# ----------------------------------------------------------------------------

def senza_accenti(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def tokenizza(s, extra_stop=()):
    s = senza_accenti(s.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    stop = STOPWORDS | set(extra_stop)
    return [t for t in s.split() if len(t) > 1 and t not in stop]


# ----------------------------------------------------------------------------
# roster
# ----------------------------------------------------------------------------

class Bambino:
    def __init__(self, n, nome, genitore, note):
        self.n = n
        self.nome = nome
        self.genitore_raw = genitore
        self.note = note
        self.sei_tu = "(tu)" in genitore
        g = re.split(r"[(,]", genitore)[0].strip()
        # se nel foglio non c'e' un nome ma solo il ruolo, sulla liberatoria
        # finisce il ruolo giusto: "papa'" non puo' diventare "la madre"
        generici = {"mamma": "la madre", "madre": "la madre",
                    "papa": "il padre", "papà": "il padre", "babbo": "il padre",
                    "padre": "il padre", "genitore": "il genitore"}
        self.genitore = generici.get(g.lower(), g) if g else "la madre"
        self.esito = None

    def __repr__(self):
        return "<%s>" % self.nome


# L'elenco dei bambini si puo' tenere in un foglio Excel, in un foglio LibreOffice
# o OpenOffice, oppure in un file di testo. Si leggono tutti e tre senza installare
# niente: dentro un .xlsx e un .ods c'e' un archivio zip con dentro dell'XML.
NOMI_ROSTER = ["01-ROSTER.xlsx", "01-ROSTER.ods", "01-ROSTER.csv", "01-ROSTER.md"]


def _colonna(rif):
    """A1 -> 0, B7 -> 1, AA3 -> 26."""
    lettere = "".join(c for c in rif if c.isalpha())
    n = 0
    for c in lettere:
        n = n * 26 + (ord(c.upper()) - 64)
    return n - 1


def righe_xlsx(path):
    with zipfile.ZipFile(path) as z:
        condivise = []
        if "xl/sharedStrings.xml" in z.namelist():
            radice = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in radice:
                condivise.append("".join(t.text or "" for t in si.iter()
                                         if t.tag.endswith("}t")))
        fogli = sorted(n for n in z.namelist()
                       if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        if not fogli:
            return []
        radice = ET.fromstring(z.read(fogli[0]))
        righe = []
        for riga in radice.iter():
            if not riga.tag.endswith("}row"):
                continue
            celle = {}
            for c in riga:
                if not c.tag.endswith("}c"):
                    continue
                tipo = c.get("t")
                testo = ""
                for figlio in c:
                    if figlio.tag.endswith("}v"):
                        testo = figlio.text or ""
                    elif figlio.tag.endswith("}is"):
                        testo = "".join(t.text or "" for t in figlio.iter()
                                        if t.tag.endswith("}t"))
                if tipo == "s" and testo.isdigit():
                    i = int(testo)
                    testo = condivise[i] if i < len(condivise) else ""
                celle[_colonna(c.get("r") or "A1")] = testo.strip()
            if celle:
                righe.append([celle.get(i, "") for i in range(max(celle) + 1)])
        return righe


def righe_ods(path):
    with zipfile.ZipFile(path) as z:
        radice = ET.fromstring(z.read("content.xml"))
    righe = []
    for riga in radice.iter():
        if not riga.tag.endswith("}table-row"):
            continue
        celle = []
        for c in riga:
            if not c.tag.endswith("}table-cell"):
                continue
            testo = " ".join(p.text or "" for p in c.iter() if p.tag.endswith("}p")).strip()
            ripetute = 1
            for k, v in c.attrib.items():
                if k.endswith("number-columns-repeated"):
                    ripetute = min(int(v), 50)   # le ultime colonne vuote si ripetono a migliaia
            celle.extend([testo] * ripetute)
        if any(celle):
            righe.append(celle)
    return righe


def righe_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fp:
        testo = fp.read()
    # Excel in italiano salva con il punto e virgola, altrove con la virgola
    separatore = ";" if testo.count(";") > testo.count(",") else ","
    return [[c.strip() for c in r] for r in csv.reader(testo.splitlines(), delimiter=separatore)]


def righe_md(path):
    righe = []
    for riga in open(path, encoding="utf-8"):
        if not riga.startswith("|"):
            continue
        righe.append([c.strip() for c in riga.strip().strip("|").split("|")])
    return righe


def trova_roster():
    trovati = [os.path.join(QUI, n) for n in NOMI_ROSTER
               if os.path.exists(os.path.join(QUI, n))]
    if not trovati:
        sys.exit("Non trovo l'elenco dei bambini. Nella cartella del programma ci deve "
                 "essere uno di questi file:\n  %s" % "\n  ".join(NOMI_ROSTER))
    if len(trovati) > 1:
        sys.exit("Trovo piu' elenchi dei bambini: %s.\n"
                 "Scegline UNO, compilalo e sposta gli altri fuori da questa cartella.\n"
                 "Poi avvia di nuovo il programma."
                 % ", ".join(os.path.basename(p) for p in trovati))
    return trovati[0]


def leggi_roster(path=None):
    path = path or ROSTER or trova_roster()
    if not os.path.exists(path):
        sys.exit("Non trovo il roster: %s" % path)
    lettori = {".xlsx": righe_xlsx, ".ods": righe_ods, ".csv": righe_csv, ".md": righe_md}
    ext = os.path.splitext(path)[1].lower()
    if ext not in lettori:
        sys.exit("Non so leggere un file %s. Usa un .xlsx, un .ods, un .csv o un .md." % ext)
    try:
        righe = lettori[ext](path)
    except Exception as e:
        sys.exit("Non riesco a leggere %s: %s\nSe l'hai aperto adesso, chiudilo e riprova."
                 % (os.path.basename(path), e))

    bambini = []
    for celle in righe:
        if len(celle) < 3 or not celle[0].isdigit():
            continue          # intestazioni, righe vuote, note sparse: si saltano
        celle = celle + [""] * (4 - len(celle))
        if "esempio: cancella" in celle[3].lower():
            sys.exit("L'elenco contiene ancora le righe di esempio. Sostituiscile con "
                     "i bambini della tua sezione prima di continuare.")
        if not celle[1].strip() or not celle[2].strip():
            sys.exit("Nell'elenco, la riga numero %s non ha il nome del bambino o "
                     "di chi risponde. Correggila e riprova." % celle[0])
        bambini.append(Bambino(int(celle[0]), celle[1], celle[2], celle[3]))
    if not bambini:
        sys.exit("In %s non trovo nessuna riga di bambino. Serve una riga per bambino, con "
                 "il numero nella prima colonna, il nome nella seconda e il genitore nella "
                 "terza." % os.path.basename(path))
    numeri = [b.n for b in bambini]
    if len(numeri) != len(set(numeri)):
        sys.exit("Nell'elenco ci sono numeri ripetuti. Ogni bambino deve avere "
                 "un numero diverso; correggi il file e riprova.")
    return bambini


# ----------------------------------------------------------------------------
# OCR locale: Tesseract su Mac, Windows e Linux; Vision come alternativa su Mac.
# ----------------------------------------------------------------------------

def tesseract_eseguibile():
    trovato = shutil.which("tesseract")
    if trovato:
        return trovato
    if sys.platform == "darwin":
        for p in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract",
                  "/opt/local/bin/tesseract"):
            if os.path.isfile(p):
                return p
    if os.name == "nt":
        p = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                         "Tesseract-OCR", "tesseract.exe")
        if os.path.isfile(p):
            return p
    return None


def ocr_disponibile():
    if tesseract_eseguibile():
        return True
    if sys.platform != "darwin":
        return False
    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError:
        return False
    return True


def ocr(path):
    exe = tesseract_eseguibile()
    if exe:
        p = subprocess.run([exe, path, "stdout", "tsv"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        if p.returncode:
            sys.exit("Non riesco a leggere lo screenshot %s: %s" %
                     (os.path.basename(path), p.stderr.strip()))
        righe_tsv = list(csv.DictReader(io.StringIO(p.stdout), delimiter="\t"))
        if not righe_tsv:
            return []
        larghezza = int(righe_tsv[0]["width"])
        altezza = int(righe_tsv[0]["height"])
        gruppi = {}
        for r in righe_tsv:
            if r["level"] != "5" or not r["text"].strip():
                continue
            chiave = (r["block_num"], r["par_num"], r["line_num"])
            gruppi.setdefault(chiave, []).append(r)
        risultato = []
        for parole in gruppi.values():
            parole.sort(key=lambda r: int(r["left"]))
            segmenti = []
            corrente = []
            for r in parole:
                x = int(r["left"])
                if corrente:
                    precedente = corrente[-1]
                    fine = int(precedente["left"]) + int(precedente["width"])
                    spazio = (x - fine) / larghezza
                    nuova_colonna = (spazio > 0.08 or
                                     (x / larghezza > 0.65 and
                                      int(corrente[0]["left"]) / larghezza < 0.55))
                    icona = (len(corrente) == 1 and
                             int(corrente[0]["left"]) / larghezza < 0.08 and
                             x / larghezza >= 0.10 and spazio > 0.02)
                    if nuova_colonna or icona:
                        segmenti.append(corrente)
                        corrente = []
                corrente.append(r)
            if corrente:
                segmenti.append(corrente)
            for segmento in segmenti:
                sinistra = min(int(r["left"]) for r in segmento)
                alto = min(int(r["top"]) for r in segmento)
                basso = max(int(r["top"]) + int(r["height"]) for r in segmento)
                risultato.append({"x": sinistra / larghezza,
                                  "y": 1 - (alto + basso) / (2 * altezza),
                                  "testo": " ".join(r["text"] for r in segmento)})
        return sorted(risultato, key=lambda r: (-r["y"], r["x"]))

    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except ImportError:
        sys.exit("Non trovo il programma OCR per leggere gli screenshot. "
                 "Leggi LEGGIMI.txt, sezione INSTALLARE OCR.")

    url = NSURL.fileURLWithPath_(os.path.abspath(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        sys.exit("Non riesco ad aprire l'immagine: %s" % path)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    righe = []

    def handler(req, err):
        for obs in req.results():
            cand = obs.topCandidates_(1)
            if not cand:
                continue
            bb = obs.boundingBox()
            righe.append({"y": bb.origin.y, "x": bb.origin.x, "testo": cand[0].string()})

    req = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(handler)
    req.setRecognitionLevel_(0)
    req.setRecognitionLanguages_(["it-IT", "en-US"])
    req.setUsesLanguageCorrection_(False)
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        img, None).performRequests_error_([req], None)

    righe.sort(key=lambda r: (-r["y"], r["x"]))
    return righe


SCARTO = [
    re.compile(r"^<+$"),
    re.compile(r"^poll votes$", re.I),
    re.compile(r"^voti del sondaggio$", re.I),
    re.compile(r"^select one or more$", re.I),
    re.compile(r"^seleziona", re.I),
    re.compile(r"^view votes$", re.I),
    re.compile(r"^vedi voti$", re.I),
    re.compile(r"^\+?[\d\s()\-\.]{7,}$"),
    re.compile(r"^(today|yesterday|oggi|ieri)\b", re.I),
    re.compile(r"^\d{1,2}[/.]\d{1,2}([/.]\d{2,4})?$"),
    re.compile(r"^\d{1,2}:\d{2}$"),
    re.compile(r"^\d+\s+vot", re.I),
    re.compile(r"^(see all|vedi tutti|mostra tutti|see votes)\b", re.I),
    re.compile(r"\?\s*$"),          # la domanda del sondaggio
]

CONTA_VOTI = re.compile(r"^(\d+)\s+vot", re.I)
ORARIO = re.compile(r"\d{1,2}:\d{2}")


def classifica_opzione(etichetta):
    e = senza_accenti(etichetta.lower()).strip(" .:!?")
    if e in ("si", "yes", "ok", "daccordo"):
        return "SI"
    if e in ("no", "non"):
        return "NO"
    if "asten" in e:
        return "ASTENUTO"
    return None


def chiave_nome(s):
    return " ".join(tokenizza(s))


def leggi_sequenza(paths, debug=False):
    """Gli screenshot, letti in ordine, come sequenza di intestazioni e nomi."""
    seq = []
    for p in paths:
        inizio = len(seq)
        righe = ocr(p)
        riepilogo = any(re.match(r"^(see all|vedi tutti|mostra tutti)\b",
                                 r["testo"], re.I) for r in righe)
        if riepilogo:
            print("\nIgnoro i nomi nella schermata riassuntiva del sondaggio: "
                  "%s. Uso solo i conteggi; i nomi vengono da 'Vedi voti'."
                  % os.path.basename(p))
        conteggi = [r for r in righe if CONTA_VOTI.match(r["testo"])]
        orari = [r for r in righe if r["x"] > 0.6 and ORARIO.search(r["testo"])]
        for r in righe:
            testo = r["testo"].strip()
            if not testo or any(rx.match(testo) for rx in SCARTO):
                if debug:
                    print("    scarto   %s" % testo)
                continue
            if not tokenizza(testo):
                continue
            if r["x"] > 0.55:
                continue
            gemello = next((c for c in conteggi if abs(c["y"] - r["y"]) < 0.02), None)
            if gemello is not None:
                n = int(CONTA_VOTI.match(gemello["testo"]).group(1))
                seq.append(("intestazione", testo, n))
                if debug:
                    print("    opzione  %s (%d voti)" % (testo, n))
            else:
                if riepilogo:
                    continue
                # ogni votante ha l'orario del voto sulla stessa riga, a destra.
                # senza orario e' intestazione, pulsante o la domanda del sondaggio.
                if not any(abs(o["y"] - r["y"]) < 0.04 for o in orari):
                    if debug:
                        print("    ignoro   %s (nessun orario accanto)" % testo)
                    continue
                seq.append(("nome", testo, None))
                if debug:
                    print("    nome     %s" % testo)
        nuove = seq[inizio:]
        if any(t == "nome" for t, _s, _n in nuove) and not any(
                t == "intestazione" for t, _s, _n in nuove):
            print("\nNello screenshot %s non si vede l'opzione del sondaggio."
                  % os.path.basename(p))
            scelta = chiedi_opzione("i voti in questo screenshot")
            seq.insert(inizio, ("intestazione", scelta, None))
    return seq


def estrai_votanti(paths, debug=False):
    """Restituisce [(nome, esito)], le attese per opzione e gli avvisi.

    I conteggi che WhatsApp scrive accanto a ogni opzione sono un vincolo, non
    un dettaglio: un'opzione con zero voti non puo' ricevere nomi, e un'opzione
    con N voti non puo' riceverne N+1. Senza questo vincolo basta che un secondo
    screenshot inquadri l'intestazione sbagliata per spostare mezza classe tra
    gli astenuti.
    """
    seq = leggi_sequenza(paths, debug)

    attese = {}
    for tipo, testo, n in seq:
        if tipo != "intestazione":
            continue
        esito = classifica_opzione(testo)
        if esito is None:
            print("  ? opzione non riconosciuta nello screenshot: %r" % testo)
            esito = chiedi_opzione(testo)
        if n is not None:
            attese[esito] = max(attese.get(esito, 0), n)

    assegnati = {}          # chiave nome -> (nome, esito)
    per_esito = {}          # esito -> quanti assegnati
    parcheggio = []         # nomi senza una casella valida
    avvisi = []
    bucket = None

    for tipo, testo, n in seq:
        if tipo == "intestazione":
            bucket = classifica_opzione(testo) or chiedi_opzione(testo)
            continue
        k = chiave_nome(testo)
        if k in assegnati:
            continue
        if bucket is None:
            parcheggio.append(testo)
            continue
        capienza = attese.get(bucket)
        if capienza is not None and per_esito.get(bucket, 0) >= capienza:
            # l'opzione corrente e' gia' piena, o ha zero voti: il nome non e' suo
            parcheggio.append(testo)
            continue
        assegnati[k] = (testo, bucket)
        per_esito[bucket] = per_esito.get(bucket, 0) + 1

    if parcheggio:
        liberi = [e for e, n in attese.items() if per_esito.get(e, 0) < n]
        if len(liberi) == 1:
            e = liberi[0]
            # prima scarto chi e' gia' a posto, poi riempio il posto che resta:
            # se taglio prima di filtrare, i duplicati si mangiano i posti liberi
            da_piazzare = [t for t in parcheggio if chiave_nome(t) not in assegnati]
            spazio = attese[e] - per_esito.get(e, 0)
            piazzati = 0
            for testo in da_piazzare[:spazio]:
                assegnati[chiave_nome(testo)] = (testo, e)
                per_esito[e] = per_esito.get(e, 0) + 1
                piazzati += 1
            if piazzati:
                avvisi.append("Ho rimesso sotto %s %d nomi che negli screenshot finivano "
                              "sotto un'opzione piena o a zero voti." % (e, piazzati))
            parcheggio = [t for t in parcheggio if chiave_nome(t) not in assegnati]
        elif len(liberi) > 1 and parcheggio and sys.stdin.isatty():
            print("\n  Questi nomi non so sotto quale opzione metterli:")
            for testo in parcheggio:
                print("    %s" % testo)
            scelta = chiedi_opzione("i nomi qui sopra")
            for testo in parcheggio:
                k = chiave_nome(testo)
                if k not in assegnati:
                    assegnati[k] = (testo, scelta)
                    per_esito[scelta] = per_esito.get(scelta, 0) + 1
            parcheggio = []
        for testo in parcheggio:
            avvisi.append("Non so sotto quale opzione sta %r: non l'ho contato." % testo)

    for esito, n in attese.items():
        letti = per_esito.get(esito, 0)
        if letti != n:
            avvisi.append("Lo screenshot dice %d voti per %s, io ne ho letti %d. "
                          "Probabilmente manca una parte della lista: rifai lo "
                          "screenshot scorrendo piu' piano." % (n, esito, letti))

    ordine = {k: i for i, (tipo, testo, _) in enumerate(seq) if tipo == "nome"
              for k in [chiave_nome(testo)]}
    votanti = sorted(assegnati.values(), key=lambda v: ordine.get(chiave_nome(v[0]), 0))
    return votanti, attese, avvisi


def voti_a_mano(bambini):
    """Nessun OCR: leggi il sondaggio e scrivi i numeri. Funziona su tutti i sistemi."""
    print("\n" + "-" * 62)
    print("  I bambini della sezione %s" % SEZIONE)
    print("-" * 62)
    for b in bambini:
        print("  %2d) %-30s risponde %s" % (b.n, b.nome, b.genitore))
    print("-" * 62)
    print("\nApri il sondaggio su WhatsApp e guarda chi ha votato cosa.")
    print("Scrivi i numeri separati da uno spazio, poi invio. Se non c'e' nessuno, invio.")

    def chiedi(etichetta):
        r = input("\n  Numeri di chi ha votato %s: " % etichetta).strip()
        return [int(x) for x in re.split(r"[\s,]+", r) if x.isdigit()]

    for etichetta in ("SI", "NO", "ASTENUTO"):
        for n in chiedi(etichetta):
            b = next((x for x in bambini if x.n == n), None)
            if b is None:
                print("    ! nel roster non c'e' nessun numero %d, lo salto" % n)
            elif b.esito:
                print("    ! %s era gia' segnato %s, lascio quello" % (b.nome, b.esito))
            else:
                b.esito = etichetta
    # chi non e' stato nominato resta non pervenuto, che e' il comportamento giusto


def correggi_voti_ocr(bambini, non_abbinati, avvisi):
    """Fa correggere solo i nomi incerti e le righe sbagliate lette dall'OCR."""
    for avviso in avvisi:
        print("\n  ATTENZIONE: %s" % avviso)
    if non_abbinati:
        print("\nL'OCR ha letto questi nomi, ma non so a quale bambino corrispondono.")
        for b in bambini:
            print("  %2d) %s" % (b.n, b.nome))
        for nome, esito in non_abbinati:
            while True:
                r = input("\n%s (%s): numero del bambino, oppure 0 se non è "
                          "nella sezione: " % (nome, esito)).strip()
                if not r.isdigit():
                    print("  Scrivi un numero dell'elenco oppure 0.")
                    continue
                if r == "0":
                    break
                b = next((x for x in bambini if x.n == int(r)), None)
                if b is None:
                    print("  Questo numero non è nell'elenco.")
                elif b.esito is not None:
                    print("  %s risulta già %s. Usa le correzioni dopo la tabella."
                          % (b.nome, b.esito))
                    break
                else:
                    b.esito = esito
                    break

    while True:
        print("\nVoti letti dagli screenshot:")
        for b in bambini:
            print("  %2d) %-30s %s" % (b.n, b.nome, b.esito or "NON PERVENUTO"))
        r = input("\nPer correggere scrivi: numero SI/NO/ASTENUTO/MANCA. "
                  "Premi Invio quando è tutto giusto: ").strip().upper()
        if not r:
            return
        pezzi = r.split()
        if len(pezzi) != 2 or not pezzi[0].isdigit() or pezzi[1] not in (
                "SI", "NO", "ASTENUTO", "MANCA"):
            print("  Esempio: 3 SI   oppure   3 MANCA")
            continue
        b = next((x for x in bambini if x.n == int(pezzi[0])), None)
        if b is None:
            print("  Questo numero non è nell'elenco.")
            continue
        b.esito = None if pezzi[1] == "MANCA" else pezzi[1]


def chiedi_opzione(etichetta):
    while True:
        r = input('    L\'opzione "%s" vale SI, NO o ASTENUTO? ' % etichetta).strip().upper()
        if r in ("SI", "NO", "ASTENUTO"):
            return r


# ----------------------------------------------------------------------------
# abbinamento nome WhatsApp -> bambino
# ----------------------------------------------------------------------------

def punteggio(tok_nome, bambino, extra_stop):
    tok_figlio = tokenizza(bambino.nome, extra_stop)
    tok_gen = tokenizza(bambino.genitore, extra_stop)
    p = 0
    for t in tok_nome:
        if t in tok_figlio:
            p += 3
        elif t in tok_gen:
            p += 3
        else:
            simili = [u for u in tok_figlio + tok_gen
                      if difflib.SequenceMatcher(None, t, u).ratio() >= 0.78]
            if simili:
                p += 2
    return p


def abbina(votanti, bambini):
    extra_stop = set()
    io_stessa = next((b for b in bambini if b.sei_tu), None)
    if io_stessa:
        # il nome della propria figlia compare come suffisso in mezza rubrica
        extra_stop |= set(tokenizza(io_stessa.nome))

    liberi = list(bambini)
    non_abbinati = []
    coppie = []

    for nome, esito in votanti:
        if re.fullmatch(r"(you|tu|io)", nome.strip(), re.I) and io_stessa in liberi:
            coppie.append((999, nome, esito, io_stessa))
            continue
        tok = tokenizza(nome, extra_stop)
        for b in bambini:
            p = punteggio(tok, b, extra_stop)
            if p >= 3:
                coppie.append((p, nome, esito, b))

    coppie.sort(key=lambda c: -c[0])
    usati_nomi, risultati = set(), []
    for p, nome, esito, b in coppie:
        if nome in usati_nomi or b not in liberi:
            continue
        usati_nomi.add(nome)
        liberi.remove(b)
        b.esito = esito
        risultati.append((nome, b, p))

    for nome, esito in votanti:
        if nome not in usati_nomi:
            non_abbinati.append((nome, esito))

    return risultati, liberi, non_abbinati


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------

def scrivi_pdf(out, evento, data_evento, bambini, data_firma, bozza, per_chat=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    L, R, T = 22 * mm, 22 * mm, 20 * mm
    W, H = A4
    TW = W - L - R
    c = canvas.Canvas(out, pagesize=A4)
    c.setAuthor(RAPPRESENTANTE)
    c.setTitle("Liberatoria foto e video - %s - Sezione %s" % (evento, SEZIONE))

    stato = {"y": H - T}

    def wrap(testo, font, size, width):
        out_, riga = [], ""
        for w in testo.split():
            t = (riga + " " + w).strip()
            if c.stringWidth(t, font, size) <= width:
                riga = t
            else:
                out_.append(riga)
                riga = w
        if riga:
            out_.append(riga)
        return out_

    def para(testo, font="Helvetica", size=10, lead=13.5, gap=5):
        c.setFont(font, size)
        for ln in wrap(testo, font, size, TW):
            c.drawString(L, stato["y"], ln)
            stato["y"] -= lead
        stato["y"] -= gap

    c.setFont("Helvetica-Bold", 13)
    c.drawString(L, stato["y"], "RIEPILOGO PER LA CHAT" if per_chat else
                 "LIBERATORIA FOTO E VIDEO - COPIA PER LA SCUOLA")
    stato["y"] -= 16
    c.drawString(L, stato["y"], "%s - SEZIONE %s" % (evento.upper(), SEZIONE))
    stato["y"] -= 15
    c.setFont("Helvetica", 10)
    for riga in (SCUOLA,
                 "%s - anno scolastico %s" % (ISTITUTO, ANNO),
                 "Evento: %s del %s" % (minuscolo(evento), data_evento)):
        c.drawString(L, stato["y"], riga)
        stato["y"] -= 12.5
    stato["y"] -= 0
    c.setLineWidth(0.7)
    c.line(L, stato["y"], W - R, stato["y"])
    stato["y"] -= 16

    if per_chat:
        para("Riepilogo dei voti raccolti nel sondaggio del gruppo WhatsApp dei genitori "
             "della sezione %s per le riprese fotografiche e video durante %s. "
             "Questa copia mostra solo i conteggi e non contiene i nomi dei bambini "
             "né le risposte individuali." % (SEZIONE, articolo(evento)), gap=7)
    else:
        para("Io %s %s, %s di %s e rappresentante di classe della sezione %s "
             "%s il %s, dichiaro di aver raccolto nel gruppo WhatsApp dei genitori della "
             "sezione il consenso alle riprese fotografiche e video dei bambini durante "
             "%s." % (g("sottoscritta", "sottoscritto"), RAPPRESENTANTE, g("madre", "padre"),
                      FIGLIO, SEZIONE, g("eletta", "eletto"), ELEZIONE, articolo(evento)), gap=7)

    para("Le immagini sono destinate alla documentazione dell'attività didattica e alla "
         "condivisione nel gruppo WhatsApp dei genitori della sezione. Non è prevista alcuna "
         "diffusione su siti o social network aperti al pubblico, né cessione a terzi per "
         "finalità commerciali. Il consenso può essere revocato in qualsiasi momento con "
         "comunicazione scritta alla scuola.", gap=10)

    conta = {e: sum(1 for b in bambini if (b.esito or "NON PERVENUTO") == e)
             for e in ("SI", "NO", "ASTENUTO", "NON PERVENUTO")}

    c.setFont("Helvetica-Bold", 10)
    c.drawString(L, stato["y"], "Esito della raccolta:")
    stato["y"] -= 14
    c.setFont("Helvetica", 10)
    for etichetta, chiave in (("Favorevoli", "SI"), ("Contrari", "NO"),
                              ("Astenuti", "ASTENUTO"), ("Non pervenuti", "NON PERVENUTO")):
        c.drawString(L + 8, stato["y"], etichetta)
        c.drawRightString(L + 115, stato["y"], str(conta[chiave]))
        stato["y"] -= 13
    stato["y"] -= 4

    if not per_chat:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(L, stato["y"], "Bambino/a")
        c.drawString(L + 78 * mm, stato["y"], "Chi risponde")
        c.drawString(L + 130 * mm, stato["y"], "Consenso")
        stato["y"] -= 4
        c.setLineWidth(0.4)
        c.line(L, stato["y"], W - R, stato["y"])
        stato["y"] -= 11
        c.setFont("Helvetica", 9)
        for b in bambini:
            c.drawString(L, stato["y"], b.nome)
            c.drawString(L + 78 * mm, stato["y"], b.genitore)
            c.drawString(L + 130 * mm, stato["y"], b.esito or "NON PERVENUTO")
            stato["y"] -= 11.5
        stato["y"] -= 2
        c.line(L, stato["y"], W - R, stato["y"])
        stato["y"] -= 14

        c.setFont("Helvetica", 9)
        c.drawString(L, stato["y"], "Fonte: elenco ufficiale della sezione e voti del sondaggio "
                                    "nel gruppo dei genitori.")
        stato["y"] -= 11.5
    esclusi = [b for b in bambini if (b.esito or "NON PERVENUTO") != "SI"]
    if esclusi:
        c.drawString(L, stato["y"], "Per i bambini non segnati come favorevoli si chiede alle "
                                    "insegnanti di non effettuare riprese.")
        stato["y"] -= 11.5
    if bozza:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(L, stato["y"], "BOZZA: manca %s." % bozza)
        stato["y"] -= 11.5
    stato["y"] -= 12

    firma_inserita = False
    if per_chat:
        para("Copia informativa per il gruppo: il documento nominativo è destinato "
             "solo alla scuola.", size=9)
    else:
        c.setFont("Helvetica", 10)
        c.drawString(L, stato["y"], "%s, %s" % (CITTA, data_firma))
        stato["y"] -= 30
        c.drawString(L, stato["y"], g("La rappresentante di classe", "Il rappresentante di classe"))
        if FIRMA and os.path.exists(FIRMA):
            try:
                img = ImageReader(FIRMA)
                iw, ih = img.getSize()
                h = 16 * mm
                c.drawImage(img, L + 2 * mm, stato["y"] - h - 4,
                            width=iw * h / ih, height=h, mask="auto")
                stato["y"] -= (h + 14)
                firma_inserita = True
            except Exception:
                print("Attenzione: non riesco a leggere l'immagine della firma. "
                      "Il PDF avrà uno spazio per firmare a mano.")
        if not firma_inserita:
            stato["y"] -= 26
            c.drawString(L, stato["y"], "Firma da apporre: __________________________")
            stato["y"] -= 16
        c.drawString(L, stato["y"], RAPPRESENTANTE)

    c.showPage()
    c.save()
    return firma_inserita


FEMMINILI = ("festa", "castagnata", "recita", "gita", "uscita", "giornata",
             "sfilata", "merenda", "visita", "passeggiata")
MASCHILI = ("laboratorio", "progetto", "saggio", "spettacolo", "concerto",
            "carnevale", "natale", "open", "pranzo")


def genere(evento):
    e = senza_accenti(evento.lower())
    if e.startswith(FEMMINILI):
        return "f"
    if e.startswith(MASCHILI):
        return "m"
    return "f" if e.split()[0].endswith("a") else "m"


def minuscolo(evento):
    """festa di Natale, non festa di natale: solo la prima parola va abbassata."""
    parole = evento.split(" ", 1)
    resto = (" " + parole[1]) if len(parole) > 1 else ""
    return parole[0].lower() + resto


def articolo(evento):
    """la castagnata, il laboratorio di ceramica, la festa di Natale"""
    return ("la " if genere(evento) == "f" else "il ") + minuscolo(evento)


def di_articolo(evento):
    """della castagnata, del laboratorio di ceramica, della festa di Natale"""
    return ("della " if genere(evento) == "f" else "del ") + minuscolo(evento)


# ----------------------------------------------------------------------------
# testi di accompagnamento
# ----------------------------------------------------------------------------

def scrivi_testi(out, evento, data_evento, bambini, firma_inserita, bozza,
                 nome_pdf_scuola, nome_pdf_chat):
    conta = {e: [b for b in bambini if (b.esito or "NON PERVENUTO") == e]
             for e in ("SI", "NO", "ASTENUTO", "NON PERVENUTO")}
    tot = len(bambini)
    si = len(conta["SI"])
    mancanti = conta["NON PERVENUTO"]

    contrari = conta["NO"]
    astenuti = conta["ASTENUTO"]
    non_autorizzati = contrari + astenuti + mancanti

    # Conteggio per la chat e per la maestra.
    pezzi = ["%s su %d famiglie" % ("nessun sì" if si == 0 else "%d sì" % si, tot)]
    if not contrari:
        pezzi.append("nessun contrario")
    elif len(contrari) == 1:
        pezzi.append("una famiglia contraria")
    else:
        pezzi.append("%d famiglie contrarie" % len(contrari))
    if len(astenuti) == 1:
        pezzi.append("una famiglia astenuta")
    elif astenuti:
        pezzi.append("%d astenute" % len(astenuti))
    riga_conteggio = ", ".join(pezzi)

    # Riga per la dirigente. Deve dire esattamente chi ha autorizzato e chi no:
    # e' il pezzo su cui la scuola si regola.
    if not non_autorizzati:
        riga_dirigente = ("Hanno risposto tutte e %d le famiglie e tutte hanno dato il consenso, "
                          "quindi l'intera sezione è autorizzata." % tot)
    else:
        voci = []
        if not contrari:
            voci.append("nessuna si è dichiarata contraria")
        elif len(contrari) == 1:
            voci.append("una si è dichiarata contraria")
        else:
            voci.append("%d si sono dichiarate contrarie" % len(contrari))
        if len(astenuti) == 1:
            voci.append("una si è astenuta")
        elif astenuti:
            voci.append("%d si sono astenute" % len(astenuti))
        if len(mancanti) == 1:
            voci.append("una non ha ancora risposto")
        elif mancanti:
            voci.append("%d non hanno ancora risposto" % len(mancanti))
        elenco = voci[0] if len(voci) == 1 else ", ".join(voci[:-1]) + " e " + voci[-1]
        riga_dirigente = ("Su %d famiglie, %s, %s. Per i bambini delle "
                          "famiglie che non hanno autorizzato chiederò alle insegnanti "
                          "di non effettuare riprese."
                          % (tot, "nessuna ha autorizzato" if si == 0
                             else "una ha autorizzato" if si == 1
                             else "%d hanno autorizzato" % si, elenco))

    if mancanti:
        riga_mancanti = ("Mancano %d risposte al sondaggio. Se non avete votato basta un clic, e "
                         "se preferite di no nessun problema: scrivetemi anche solo in privato e "
                         "chiedo alle maestre di non fotografare il vostro bambino."
                         % len(mancanti))
        if len(mancanti) == 1:
            riga_mancanti = ("Manca una sola risposta al sondaggio. Se non hai votato basta un "
                             "clic, e se preferisci di no nessun problema: scrivimi anche solo in "
                             "privato e chiedo alle maestre di non fotografare il tuo bambino.")
    elif non_autorizzati:
        riga_mancanti = ("Hanno risposto tutte. Per i bambini delle famiglie che non hanno "
                         "autorizzato chiederò alle maestre di non fotografare.")
    else:
        riga_mancanti = "Hanno risposto tutte, quindi l'intera sezione è autorizzata."

    testo = """MESSAGGI PER %s
Generato il %s. Testi pronti da incollare, nessuna formattazione.

ALLEGATI: alla scuola %s; alla chat dei genitori %s.
Non inviare alla chat il PDF per la scuola: contiene nomi e risposte individuali.


--------------------------------------------------------------
EMAIL ALLA DIRIGENTE
Allegato: il PDF nominativo per la scuola
--------------------------------------------------------------

OGGETTO: %s, sezione %s - liberatoria foto e video per %s

Gentile Dirigente,

sono %s, %s di %s e rappresentante di classe della sezione %s
(%s), %s lo scorso %s.

Le allego la liberatoria per le riprese fotografiche e video %s del %s. Ho raccolto il
consenso delle famiglie con un sondaggio nel gruppo dei genitori. %s

Le immagini servono alla documentazione dell'attività e alla condivisione nel gruppo
WhatsApp dei genitori della sezione. Non è prevista nessuna pubblicazione su siti o social
network aperti al pubblico.

Se la liberatoria generale firmata all'iscrizione copre già questo utilizzo, mi basta
saperlo e non vi faccio arrivare un documento in più a ogni iniziativa.

Resto a disposizione per qualsiasi chiarimento.

Grazie e buon lavoro,

%s
Rappresentante di classe, sezione %s


--------------------------------------------------------------
MESSAGGIO PER LA CHAT DEI GENITORI
--------------------------------------------------------------

Buongiorno a tutti! Grazie per i voti sul sondaggio delle foto %s.
Siamo a %s.

Vi allego il riepilogo per la chat, con i soli conteggi e senza nomi dei bambini:
le foto e i video servono per documentare l'attività e per condividerli qui nel gruppo,
niente social e niente pubblicazioni fuori da qui.

%s

Grazie!


--------------------------------------------------------------
MESSAGGIO PER LA MAESTRA
--------------------------------------------------------------

Buongiorno maestra! Le lascio il PDF per la scuola per le foto %s: %s. Grazie!
""" % (evento.upper(), oggi_esteso(), nome_pdf_scuola, nome_pdf_chat,
       SCUOLA, SEZIONE, articolo(evento),
       RAPPRESENTANTE, g("mamma", "papà"), FIGLIO, SEZIONE, SCUOLA,
       g("eletta", "eletto"), ELEZIONE, di_articolo(evento), data_evento, riga_dirigente,
       RAPPRESENTANTE, SEZIONE, di_articolo(evento), riga_conteggio, riga_mancanti,
       di_articolo(evento), riga_conteggio)

    da_fare = []
    if not firma_inserita:
        da_fare.append("Firma il PDF per la scuola prima di inviarlo. Contiene solo uno "
                       "spazio vuoto per la firma.")
    if bozza:
        da_fare.append("Manca la data dell'evento: i PDF sono BOZZE. Rigenera i file "
                       "con la data prima di inviarli.")
    if da_fare:
        testo = ("ATTENZIONE - PRIMA DI INVIARE\n" + "\n".join(da_fare) +
                 "\n\n" + testo)

    if mancanti:
        uno = len(mancanti) == 1
        testo += """

--------------------------------------------------------------
DA FARE PRIMA DI MANDARE
--------------------------------------------------------------

Non %s ancora votato:

%s

Un voto che manca non e' un no: e' un non pervenuto, e si tratta come tale. Meglio un
bambino fuori dalle foto che un consenso dato per scontato.

%s in privato costa meno di un tag nel gruppo, e di solito funziona meglio.
""" % ("ha" if uno else "hanno",
       "\n".join("  - %s, risponde %s" % (b.nome, b.genitore) for b in mancanti),
       "Un messaggio" if uno else "Un messaggio a testa")

    open(out, "w", encoding="utf-8").write(testo)


def oggi_esteso(d=None):
    d = d or dt.date.today()
    return "%d %s %d" % (d.day, MESI[d.month - 1], d.year)


# ----------------------------------------------------------------------------
# interfaccia
# ----------------------------------------------------------------------------

def screenshot_recenti(n=6):
    cartelle = [os.path.expanduser("~/" + c) for c in
                ("Desktop", "Downloads", "Scrivania", "Scaricati", "Immagini", "Pictures")]
    trovati = []
    for c in cartelle:
        if not os.path.isdir(c):
            continue
        for f in os.listdir(c):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                p = os.path.join(c, f)
                trovati.append((os.path.getmtime(p), p))
    trovati.sort(reverse=True)
    return [p for _, p in trovati[:n]]


def scegli_file_immagini():
    """Apre il selettore del sistema, quando disponibile."""
    if sys.platform == "darwin":
        script = ('set scelti to choose file with prompt "Scegli gli screenshot del '
                  'sondaggio (puoi selezionarne piu di uno)" with multiple selections allowed\n'
                  'set risultato to ""\n'
                  'repeat with f in scelti\n'
                  'set risultato to risultato & POSIX path of f & linefeed\n'
                  'end repeat\n'
                  'return risultato')
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if p.returncode == 0:
            return [r for r in p.stdout.splitlines() if r.strip()]
        return []
    try:
        import tkinter as tk
        from tkinter import filedialog
        finestra = tk.Tk()
        finestra.withdraw()
        paths = filedialog.askopenfilenames(
            title="Scegli gli screenshot del sondaggio",
            filetypes=[("Immagini", "*.png *.jpg *.jpeg"), ("Tutti i file", "*.*")])
        finestra.destroy()
        return list(paths)
    except Exception:
        return []


def chiedi_screenshot():
    print("\nScegli gli screenshot del sondaggio nella finestra che si apre.")
    print("Se ne hai più di uno, selezionali tutti insieme.")
    scelti = scegli_file_immagini()
    if scelti:
        return scelti
    recenti = screenshot_recenti()
    if recenti:
        print("\nUltime immagini trovate sul computer:\n")
        for i, p in enumerate(recenti, 1):
            quando = dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%d/%m %H:%M")
            print("  %d) %s  %s" % (i, quando, os.path.basename(p)))
        print("\nScrivi i numeri degli screenshot del sondaggio, nell'ordine in cui li hai fatti")
        print("(esempio: 2 1), oppure trascina qui i file e premi invio.")
    else:
        print("\nNon trovo immagini recenti. Trascina qui gli screenshot e premi invio.")
    scelta = input("\n> ").strip()
    if not scelta:
        sys.exit("Nessuno screenshot, nessuna liberatoria.")
    if re.fullmatch(r"[\d\s,]+", scelta):
        idx = [int(x) for x in re.split(r"[\s,]+", scelta) if x]
        return [recenti[i - 1] for i in idx if 1 <= i <= len(recenti)]
    return [p.strip().strip("'\"") for p in re.findall(r"(?:'[^']*'|\"[^\"]*\"|\S+)", scelta)]


def normalizza_data(s):
    s = s.strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", s)
    if m:
        g, me, a = int(m.group(1)), int(m.group(2)), m.group(3)
        a = int(a) if a else dt.date.today().year
        if a < 100:
            a += 2000
        try:
            return oggi_esteso(dt.date(a, me, g))
        except ValueError:
            raise ValueError("La data %s non esiste. Scrivila come giorno/mese/anno, "
                             "per esempio 12/11/2026." % s)
    return s


def verifica_cartella_locale():
    """Evita di sincronizzare nomi, esiti e immagine della firma per errore."""
    parti = os.path.realpath(QUI).replace("\\", "/").lower().split("/")
    if any(p.startswith(("dropbox", "onedrive")) or p in
           ("cloudstorage", "mobile documents", "icloud drive") for p in parti):
        sys.exit("Questa cartella si trova in un servizio cloud. Qui i dati dei bambini "
                 "e la tua firma potrebbero essere sincronizzati.\n"
                 "Copia lo ZIP in una cartella locale non sincronizzata, estrailo "
                 "e avvia il programma da quella copia. Leggi LEGGIMI.txt.")


def mostra_cartella(path):
    """Apre la cartella del PDF appena fatto, su qualsiasi sistema. Se non riesce, pazienza."""
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.call(["open", "-R", path])
        elif os.name == "nt":
            subprocess.call(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.call(["xdg-open", os.path.dirname(path)])
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Genera la liberatoria foto e video dagli screenshot del sondaggio.")
    ap.add_argument("screenshot", nargs="*", help="immagini dei voti del sondaggio, in ordine")
    ap.add_argument("--evento", help='nome dell\'evento, es. "Castagnata"')
    ap.add_argument("--data", help='data dell\'evento, es. "12 novembre 2026" o 12/11')
    ap.add_argument("--si", action="store_true",
                    help="salta la conferma solo quando i voti sono inseriti con --mano")
    ap.add_argument("--mano", action="store_true",
                    help="segna i voti a mano invece di leggere gli screenshot")
    ap.add_argument("--debug", action="store_true",
                    help="mostra riga per riga cosa legge negli screenshot")
    args = ap.parse_args()

    verifica_cartella_locale()
    roster = trova_roster()
    bambini = leggi_roster(roster)
    carica_dati()

    print("\n" + "=" * 62)
    print("  LIBERATORIA FOTO E VIDEO - sezione %s" % SEZIONE)
    print("=" * 62)

    print("\nElenco: %d bambini letti da %s" % (len(bambini), os.path.basename(roster)))

    attese, non_abbinati, avvisi = {}, [], []
    if args.mano:
        voti_a_mano(bambini)
    else:
        if not ocr_disponibile():
            sys.exit("Non trovo un programma OCR per leggere gli screenshot. "
                     "Leggi LEGGIMI.txt, sezione INSTALLARE OCR. "
                     "Puoi usare --mano solo se vuoi inserire i voti a mano.")
        paths = args.screenshot or chiedi_screenshot()
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            sys.exit("Nessuno degli screenshot indicati esiste.")

        print("\nLeggo gli screenshot nell'ordine scelto:")
        for p in paths:
            quando = dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M")
            print("  %s  %s" % (quando, os.path.basename(p)))
        votanti, attese, avvisi = estrai_votanti(paths, args.debug)
        if not votanti:
            sys.exit("Non ho letto nessun votante dagli screenshot. Rifalli mostrando "
                     "nomi e orari, poi riprova. Nessun PDF è stato creato.")
        _risultati, _mancanti, non_abbinati = abbina(votanti, bambini)
        correggi_voti_ocr(bambini, non_abbinati, avvisi)
        avvisi, non_abbinati = [], []

    print("\n" + "-" * 62)
    for b in bambini:
        marchio = {"SI": "si", "NO": "NO", "ASTENUTO": "ast"}.get(b.esito, "  manca")
        print("  %-28s %-22s %s" % (b.nome, b.genitore, marchio))
    print("-" * 62)

    conta = {}
    for b in bambini:
        k = b.esito or "NON PERVENUTO"
        conta[k] = conta.get(k, 0) + 1
    print("  favorevoli %d   contrari %d   astenuti %d   non pervenuti %d"
          % (conta.get("SI", 0), conta.get("NO", 0),
             conta.get("ASTENUTO", 0), conta.get("NON PERVENUTO", 0)))

    for a in avvisi:
        print("\n  ATTENZIONE: %s" % a)
    if non_abbinati:
        print("\n  %s ad abbinare questi nomi:"
              % g("Non sono riuscita", "Non sono riuscito"))
        for nome, esito in non_abbinati:
            print("    %s  (%s)" % (nome, esito))
        print("  Controlla che il nome nel roster e quello in rubrica abbiano almeno")
        print("  una parola in comune, poi rilancia.")

    evento = args.evento or input("\nNome dell'evento (es. Castagnata): ").strip()
    if not evento:
        sys.exit("Serve il nome dell'evento.")
    while True:
        data_grezza = args.data if args.data is not None else input(
            "Data dell'evento (es. 12/11/2026, invio se non la sai ancora): ").strip()
        try:
            data_evento = normalizza_data(data_grezza) if data_grezza else "______________"
            break
        except ValueError as e:
            if args.data is not None:
                sys.exit(str(e))
            print("  %s" % e)

    bozza = None
    if data_evento.startswith("___"):
        bozza = "la data dell'evento"

    if not (args.si and args.mano):
        if input("\nControlla la tabella sopra. Scrivi CONFERMO per creare i file: ").strip().upper() != "CONFERMO":
            sys.exit("Annullato. Nessun file creato.")

    slug = re.sub(r"[^A-Za-z0-9]+", "-", senza_accenti(evento)).strip("-").title()
    pdf = os.path.join(QUI, "Liberatoria-%s-Scuola.pdf" % slug)
    pdf_chat = os.path.join(QUI, "Riepilogo-%s-Chat.pdf" % slug)
    txt = os.path.join(QUI, "Messaggi-%s.txt" % slug)
    firma_inserita = scrivi_pdf(pdf, evento, data_evento, bambini, oggi_esteso(), bozza)
    scrivi_pdf(pdf_chat, evento, data_evento, bambini, oggi_esteso(), bozza, per_chat=True)
    scrivi_testi(txt, evento, data_evento, bambini, firma_inserita, bozza,
                 os.path.basename(pdf), os.path.basename(pdf_chat))

    print("\nFatto:")
    print("  %s" % pdf)
    print("  %s" % pdf_chat)
    print("  %s" % txt)
    if not firma_inserita:
        print("\nPrima di mandare il PDF alla scuola, firmalo: per ora ha solo uno spazio vuoto.")
    if bozza:
        print("\nIl PDF esce marcato BOZZA finché non metti la data. Rilancia con --data quando ce l'hai.")
    mostra_cartella(pdf)


if __name__ == "__main__":
    main()
