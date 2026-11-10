#!/bin/bash
# MAC: doppio clic su questo file e parte tutto.
# La prima volta ci mette un minuto: si installa da sola quello che le serve.
# Se il doppio clic non funziona, clic destro sul file e poi "Apri".

cd "$(dirname "$0")" || exit 1

VENV="$HOME/Library/Application Support/Liberatorie-classe/venv"

# Cerca un Python abbastanza recente. reportlab, che fa il PDF, vuole almeno il 3.10:
# il Python di sistema del Mac e' il 3.9, quindi se e' l'unico che c'e' si installa
# una versione piu' vecchia di reportlab, che con il 3.9 funziona.
PY=""
VECCHIO=""
for C in python3.14 python3.13 python3.12 python3.11 python3.10 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  P="$(command -v "$C" 2>/dev/null)" || continue
  [ -x "$P" ] || continue
  if "$P" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$P"; break
  fi
done
if [ -z "$PY" ] && [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
  VECCHIO="si"
fi
if [ -z "$PY" ]; then
  echo "Su questo Mac non trovo Python. Apri il Terminale e scrivi:  python3"
  echo "Il Mac ti proporra' di installarlo. Poi riprova con questo file."
  echo; echo "Premi invio per chiudere."; read -r; exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Prima volta: preparo l'ambiente, ci vuole un minuto."
  mkdir -p "$(dirname "$VENV")"
  "$PY" -m venv "$VENV" || { echo "Non riesco a creare l'ambiente."; read -r; exit 1; }
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  if [ -n "$VECCHIO" ]; then
    REPORTLAB="reportlab<4"
  else
    REPORTLAB="reportlab"
  fi
  "$VENV/bin/python" -m pip install --quiet "$REPORTLAB" \
    || { echo "Installazione fallita. Serve una connessione a internet."; read -r; exit 1; }
  # Se Tesseract e' presente, basta quello. Altrimenti installa Vision.
  if ! command -v tesseract >/dev/null 2>&1 &&
     [ ! -x /opt/homebrew/bin/tesseract ] &&
     [ ! -x /usr/local/bin/tesseract ] &&
     [ ! -x /opt/local/bin/tesseract ]; then
    "$VENV/bin/python" -m pip install --quiet \
      pyobjc-framework-Vision pyobjc-framework-Quartz 2>/dev/null \
      || echo "Vision non installato. Se serve, installa Tesseract OCR (vedi LEGGIMI.txt)."
  fi
  echo "Pronto."
fi

"$VENV/bin/python" genera.py "$@"

echo
echo "Premi invio per chiudere."
read -r
