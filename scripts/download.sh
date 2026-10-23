#!/usr/bin/env sh
# Baixa do ONS Dados Abertos os parquets mensais de constrained-off (eólica e fotovoltaica),
# por conjunto (_tm) e por usina (_detail_tm), para <dest>/{eol,sol,det}.
# Uso: sh scripts/download.sh data/raw
set -eu
DEST=${1:-data/raw}
B=https://ons-aws-prod-opendata.s3.amazonaws.com
mkdir -p "$DEST/eol" "$DEST/sol" "$DEST/det"
curl -sS -m 120 "$B/?list-type=2&prefix=dataset/restricao_coff" -o "$DEST/list.xml"
grep -oE 'dataset/restricao_coff_(eolica|fotovoltaica)(_detail)?_tm/[A-Z_0-9]+\.parquet' "$DEST/list.xml" |
  xargs -P 8 -I{} sh -c '
    case {} in *detail*) d=det;; *eolica*) d=eol;; *) d=sol;; esac
    curl -sS -m 600 --retry 3 -o "'"$DEST"'/$d/$(basename {})" "'"$B"'/{}"'
echo "ok: $(ls "$DEST"/eol | wc -l) eólica, $(ls "$DEST"/sol | wc -l) solar, $(ls "$DEST"/det | wc -l) detalhe"
