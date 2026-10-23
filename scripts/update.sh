#!/usr/bin/env sh
# Atualização completa: baixa os dados do ONS, recalcula e regenera o site (docs/).
# Uso: sh scripts/update.sh [pasta_dados_brutos]
set -eu
RAW=${1:-data/raw}
sh scripts/download.sh "$RAW"
python3 -I scripts/build.py "$RAW" data/processed/out.json
python3 -I scripts/tables.py data/processed/out.json data/processed
python3 -I scripts/build_site.py dashboard/index.html data/processed docs
