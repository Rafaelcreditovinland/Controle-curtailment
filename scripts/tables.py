"""Turn out.json into the dashboard's CSV datasets.

Usage: python3 -I tables.py <out.json> <dest_dir>
"""
import csv
import json
import sys

import numpy as np

o = json.load(open(sys.argv[1]))
DEST = sys.argv[2]
LTM = ("2025-10-01", "2026-09-01")
PREV = ("2024-10-01", "2025-09-01")
PARTIAL = "2026-10-01"  # ONS file ends 2026-10-21

NOMES = {"EOL_SIN": "Eólica · SIN", "EOL_NE": "Eólica · Nordeste", "UFV_SIN": "Solar · SIN",
         "UFV_SE": "Solar · Sudeste/C-Oeste", "NE_ALL": "Nordeste · eólica + solar",
         "SE_ALL": "Sudeste/C-Oeste · eólica + solar"}
EOL_KEYS = ("assurua", "serido", "mirante", "icarai", "taiba", "amontada", "riachao", "tupi")
REFS = {k: ("EOL_SIN", "EOL_NE", "NE_ALL") for k in EOL_KEYS} | {"luizcarlos": ("UFV_SIN", "UFV_SE", "SE_ALL")}
PEERS = {k: "EOL_NE" for k in EOL_KEYS} | {"luizcarlos": "UFV_SE"}

PAI = {k: v.get("pai", "") for k, v in o["complexos"].items()}
groups = {k: (v["nome"], "complexo", v["serie"]) for k, v in o["complexos"].items()}
groups |= {k: (NOMES[k], "referencia", v) for k, v in o["bench"].items()}


def cut(r):
    return r["ene"] + r["cnf"] + r["rel"] + r["par"]


def window(s, a, b):
    rs = [r for r in s if a <= r["mes"] <= b]
    pot = sum(r["ger"] + cut(r) for r in rs)
    if not rs or not pot:
        return None
    return dict(meses=len(rs), pot=pot, cut=sum(cut(r) for r in rs),
                **{k: sum(r[k] for r in rs) for k in ("ene", "cnf", "rel", "par", "loc")})


def r1(x, n=2):
    return None if x is None else round(x, n)


serie, resumo = [], []
for g, (nome, tipo, s) in groups.items():
    s = [r for r in s if r["ger"] + cut(r) > 0]
    for i, r in enumerate(s):
        pot = r["ger"] + cut(r)
        prev12 = [x for x in s if x["mes"] <= r["mes"]][-12:]
        mi = lambda m: int(m[:4]) * 12 + int(m[5:7])
        full = len(prev12) == 12 and mi(r["mes"]) - mi(prev12[0]["mes"]) == 11 and r["mes"] != PARTIAL
        w = window(prev12, prev12[0]["mes"], r["mes"]) if full else None
        serie.append(dict(
            grupo=g, nome=nome, tipo=tipo, mes=r["mes"][:7], parcial="sim" if r["mes"] == PARTIAL else "não",
            geracao_mwh=r1(r["ger"], 0), potencial_mwh=r1(pot, 0), cortado_mwh=r1(cut(r), 0),
            ene_mwh=r1(r["ene"], 0), cnf_mwh=r1(r["cnf"], 0), rel_mwh=r1(r["rel"], 0), par_mwh=r1(r["par"], 0),
            local_mwh=r1(r["loc"], 0),
            pct_cortado=r1(100 * cut(r) / pot), pct_ene=r1(100 * r["ene"] / pot), pct_cnf=r1(100 * r["cnf"] / pot),
            pct_rel=r1(100 * r["rel"] / pot), pct_local=r1(100 * r["loc"] / pot),
            pct_12m=r1(100 * w["cut"] / w["pot"]) if w else None))

    w, p = window(s, *LTM), window(s, *PREV)
    m12 = [x for x in serie if x["grupo"] == g and LTM[0][:7] <= x["mes"] <= LTM[1][:7]]
    slope = float(np.polyfit(range(len(m12)), [x["pct_cortado"] for x in m12], 1)[0]) if len(m12) >= 6 else None
    resumo.append(dict(
        grupo=g, nome=nome, tipo=tipo, controladora=PAI.get(g, ""), janela="out/25–set/26", meses=w["meses"],
        potencial_gwh=r1(w["pot"] / 1e3, 1), cortado_gwh=r1(w["cut"] / 1e3, 1),
        pct_12m=r1(100 * w["cut"] / w["pot"]), pct_ene=r1(100 * w["ene"] / w["pot"]),
        pct_cnf=r1(100 * w["cnf"] / w["pot"]), pct_rel=r1(100 * w["rel"] / w["pot"]),
        pct_local=r1(100 * w["loc"] / w["pot"]),
        pct_12m_anterior=r1(100 * p["cut"] / p["pot"]) if p else None,
        delta_pp=r1(100 * w["cut"] / w["pot"] - 100 * p["cut"] / p["pot"]) if p else None,
        tendencia_pp_mes=r1(slope),
        pct_set26=next(x["pct_cortado"] for x in serie if x["grupo"] == g and x["mes"] == "2026-09")))

by = {r["grupo"]: r for r in resumo}
pares = []
for k, ref in PEERS.items():
    for p in o["peers"][ref]:
        pares.append(dict(id=f"{ref}:{p['id']}", grupo_pares=ref, nome=p["nome"], uf=p["uf"], destaque="",
                          potencial_gwh=r1((p["ger"] + p["cut"]) / 1e3, 1),
                          pct_12m=r1(100 * p["cut"] / (p["ger"] + p["cut"]))))
pares = list({p["id"]: p for p in pares}.values())
for k, ref in PEERS.items():
    if PAI.get(k):  # only the consolidating company is shown among peers
        continue
    pares.append(dict(id=f"{ref}:{k}", grupo_pares=ref, nome=by[k]["nome"], uf="", destaque=k,
                      potencial_gwh=by[k]["potencial_gwh"], pct_12m=by[k]["pct_12m"]))

for k, refs in REFS.items():
    r = by[k]
    peer = [p["pct_12m"] for p in pares if p["grupo_pares"] == PEERS[k] and not p["destaque"]]
    r["percentil_pares"] = r1(100 * np.mean([x <= r["pct_12m"] for x in peer]), 0)
    r["n_pares"] = len(peer)
    r["mediana_pares"] = r1(float(np.median(peer)))
    for lab, ref in zip(("fonte_sin", "fonte_sub", "sub"), refs):
        r[f"ref_{lab}"] = ref
        r[f"pct_ref_{lab}"] = by[ref]["pct_12m"]
        r[f"spread_{lab}_pp"] = r1(r["pct_12m"] - by[ref]["pct_12m"])
    a = {x["mes"]: x["pct_cortado"] for x in serie if x["grupo"] == k and x["parcial"] == "não"}
    b = {x["mes"]: x["pct_cortado"] for x in serie if x["grupo"] == refs[1] and x["parcial"] == "não"}
    ms = sorted(set(a) & set(b))[-24:]
    r["correl_fonte_sub"] = r1(float(np.corrcoef([a[m] for m in ms], [b[m] for m in ms])[0, 1])) if len(ms) >= 6 else None
    r["meses_correl"] = len(ms)

usinas = [dict(complexo=m["complexo"], usina=m["usina"], id_ons=m["id_ons"], ceg=m["ceg"],
               conjunto_ons=m["conjunto"], id_conjunto=m["id_conjunto"], de=m["inicio"], ate=m["fim"])
          for m in o["mapa"]]


def write(name, rows):
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(f"{DEST}/{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    print(name, len(rows), cols)


write("serie_mensal", serie)
write("resumo_12m", resumo)
write("pares_12m", pares)
write("usinas", usinas)
