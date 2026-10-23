# Controle de curtailment

Controle mensal de curtailment (constrained-off) dos ativos de geração renovável com exposição via debêntures, a partir do ONS Dados Abertos.

Ativos: Assuruá 4 e 5 (Serena), Luiz Carlos (Atlas, Boa Sorte 9–17), Serra do Seridó (EDF, X–XVII), Oeste Seridó / Mirante (Elera) e Tupi (Ibitu: Icaraí, Taíba, Amontada, Riachão).

## Fonte
ONS Dados Abertos, `ons-aws-prod-opendata.s3.amazonaws.com/dataset/`:
- `restricao_coff_eolica_tm` e `restricao_coff_fotovoltaica_tm` (por usina/conjunto)
- `restricao_coff_eolica_detail_tm` e `restricao_coff_fotovoltaica_detail_tm` (por usina)

Eólica desde out/21; solar desde abr/24.

## Como rodar
```sh
pip install duckdb pyarrow numpy
sh scripts/download.sh data/raw              # ~950 MB, fora do git
python3 -I scripts/build.py data/raw data/processed/out.json
python3 -I scripts/tables.py data/processed/out.json data/processed
```
`build.py` define os complexos (lista de códigos ONS por usina) e as referências; `tables.py` gera os CSVs do painel.

## Saídas (`data/processed/`)
- `serie_mensal.csv`: geração, corte por motivo (ENE, CNF, REL, PAR) e origem local, % cortado e acumulado 12 meses, por complexo e referência
- `resumo_12m.csv`: 12 meses, comparação com fonte/submercado, tendência, correlação, percentil; `controladora` liga complexos à empresa consolidadora
- `pares_12m.csv`: % cortado em 12 meses de cada usina/conjunto da mesma fonte e submercado
- `usinas.csv`: mapeamento das usinas (código ONS, CEG) por complexo

## Método
- Energia cortada = `val_geracaonaorealizadaapurada` (MWmed × 0,5 h); potencial = gerado + cortado.
- Referências: média ponderada da fonte (SIN e submercado) e do submercado, excluindo os conjuntos dos ativos.
- Ativo dentro de conjunto compartilhado: corte do conjunto rateado pela diferença positiva entre estimada (corrigida pelo viés mensal da usina) e verificada, nas usinas restritas.

## Painel
`dashboard/index.html` é a página do painel publicado no Claude (tipo Dashboard), que lê os CSVs acima.
