#!/bin/bash
# LINUX: apri il Terminale nella cartella di questo file e scrivi:  ./Liberatoria.sh
# La prima volta ci mette un minuto: si installa da sola quello che le serve.

cd "$(dirname "$0")" || exit 1

VENV="${XDG_DATA_HOME:-$HOME/.local/share}/liberatorie-classe/venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Non trovo Python. Installalo con uno di questi, secondo la tua distribuzione:"
  echo "  Debian, Ubuntu, Mint:  sudo apt install python3 python3-venv"
  echo "  Fedora:                sudo dnf install python3"
  echo "  Arch:                  sudo pacman -S python"
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Prima volta: preparo l'ambiente, ci vuole un minuto."
  mkdir -p "$(dirname "$VENV")"
  if ! python3 -m venv "$VENV"; then
    echo "Non riesco a creare l'ambiente. Su Debian e Ubuntu manca un pezzo:"
    echo "  sudo apt install python3-venv"
    exit 1
  fi
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet reportlab \
    || { echo "Installazione fallita. Serve una connessione a internet."; exit 1; }
  echo "Pronto."
fi

# Legge gli screenshot con Tesseract OCR, installato sul computer.
"$VENV/bin/python" genera.py "$@"
