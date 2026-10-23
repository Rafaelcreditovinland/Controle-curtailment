"""Turn out.json into the dashboard's CSV datasets.

Usage: python3 -I tables.py <out.json> <dest_dir>
"""
import csv
import json
import sys

import numpy as np

o = json.load(open(sys.argv[1]))
DEST = sys.argv[2]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def mes_label(m):
    return f"{MESES[int(m[5:7]) - 1]}/{m[2:4]}"


def shift(m, k):
    i = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}-01"


# Windows come from the data: last 12 complete months, and the 12 before them.
LTM = (o["meta"]["ltm"]["ini"], o["meta"]["ltm"]["fim"])
PREV = (shift(LTM[0], -12), shift(LTM[1], -12))
PARTIAL = o["meta"]["ltm"]["parcial"]  # month still being published by ONS, "" if none
JANELA = f"{mes_label(LTM[0])}–{mes_label(LTM[1])}"
ULTIMO = o["meta"]["ultimo_instante"]
DADOS_ATE = f"{ULTIMO[8:10]}/{mes_label(ULTIMO)}"

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
        grupo=g, nome=nome, tipo=tipo, controladora=PAI.get(g, ""), janela=JANELA, ultimo_mes=mes_label(LTM[1]),
        dados_ate=DADOS_ATE, meses=w["meses"],
        potencial_gwh=r1(w["pot"] / 1e3, 1), cortado_gwh=r1(w["cut"] / 1e3, 1),
        pct_12m=r1(100 * w["cut"] / w["pot"]), pct_ene=r1(100 * w["ene"] / w["pot"]),
        pct_cnf=r1(100 * w["cnf"] / w["pot"]), pct_rel=r1(100 * w["rel"] / w["pot"]),
        pct_local=r1(100 * w["loc"] / w["pot"]),
        pct_12m_anterior=r1(100 * p["cut"] / p["pot"]) if p else None,
        delta_pp=r1(100 * w["cut"] / w["pot"] - 100 * p["cut"] / p["pot"]) if p else None,
        tendencia_pp_mes=r1(slope),
        pct_ultimo_mes=next(x["pct_cortado"] for x in serie if x["grupo"] == g and x["mes"] == LTM[1][:7])))

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


# ---------- System-wide view (all ONS plants, assets included) ----------
SUBS = {"NE": "Nordeste", "SE": "Sudeste/C-Oeste", "S": "Sul", "N": "Norte"}
FONTES = {"EOL": "Eólica", "UFV": "Solar", "TOTAL": "Eólica + solar"}
sis = o["sistema"]


def agg(rows):
    a = {k: sum(r[k] for r in rows) for k in ("ger", "ene", "cnf", "rel", "par", "loc")}
    a["cut"] = a["ene"] + a["cnf"] + a["rel"] + a["par"]
    a["pot"] = a["ger"] + a["cut"]
    return a


def pcts(a):
    p = a["pot"] or None
    return dict(pct_cortado=r1(100 * a["cut"] / p) if p else None, pct_ene=r1(100 * a["ene"] / p) if p else None,
                pct_cnf=r1(100 * a["cnf"] / p) if p else None, pct_rel=r1(100 * a["rel"] / p) if p else None,
                pct_local=r1(100 * a["loc"] / p) if p else None)


sin_mensal = []
meses = sorted({r["mes"] for r in sis})
for f in ("EOL", "UFV", "TOTAL"):
    for sub in ("SIN", *SUBS):
        for m in meses:
            rows = [r for r in sis if r["mes"] == m and (f == "TOTAL" or r["fonte"] == f) and (sub == "SIN" or r["sub"] == sub)]
            # Solar is only published from Apr/24; before that a "total" would be wind only.
            if not rows or (f == "TOTAL" and m < o["meta"]["inicio"]["UFV"]):
                continue
            a = agg(rows)
            if not a["pot"]:
                continue
            sin_mensal.append(dict(fonte=f, fonte_nome=FONTES[f], submercado=sub, submercado_nome=SUBS.get(sub, "SIN"),
                                   mes=m[:7], parcial="sim" if m == PARTIAL else "não",
                                   potencial_gwh=r1(a["pot"] / 1e3, 1), geracao_gwh=r1(a["ger"] / 1e3, 1),
                                   cortado_gwh=r1(a["cut"] / 1e3, 1), ene_gwh=r1(a["ene"] / 1e3, 1),
                                   cnf_gwh=r1(a["cnf"] / 1e3, 1), rel_gwh=r1(a["rel"] / 1e3, 1),
                                   par_gwh=r1(a["par"] / 1e3, 1), local_gwh=r1(a["loc"] / 1e3, 1), **pcts(a)))

sistema_12m = []
for f in ("EOL", "UFV", "TOTAL"):
    for sub in ("SIN", *SUBS):
        sel = lambda r, a, b: a <= r["mes"] <= b and (f == "TOTAL" or r["fonte"] == f) and (sub == "SIN" or r["sub"] == sub)
        a = agg([r for r in sis if sel(r, *LTM)])
        if not a["pot"]:
            continue
        p = agg([r for r in sis if sel(r, *PREV)])
        if f == "TOTAL" and PREV[0] < o["meta"]["inicio"]["UFV"]:
            p = {"pot": 0}
        last = agg([r for r in sis if sel(r, LTM[1], LTM[1])])
        pc = pcts(a)
        sistema_12m.append(dict(chave=f"{f}_{sub}", fonte=f, fonte_nome=FONTES[f], submercado=sub,
                                submercado_nome=SUBS.get(sub, "SIN"), janela=JANELA, ultimo_mes=mes_label(LTM[1]),
                                dados_ate=DADOS_ATE, potencial_gwh=r1(a["pot"] / 1e3, 1),
                                cortado_gwh=r1(a["cut"] / 1e3, 1), **pc,
                                pct_12m_anterior=r1(100 * p["cut"] / p["pot"]) if p["pot"] else None,
                                delta_pp=r1(pc["pct_cortado"] - 100 * p["cut"] / p["pot"]) if p["pot"] else None,
                                cortado_ultimo_mes_gwh=r1(last["cut"] / 1e3, 1),
                                pct_ultimo_mes=pcts(last)["pct_cortado"]))

uf_12m = []
NOMES_UF = {g["uf"]: g["nome"] for g in json.load(open(f"{DEST}/mapa_uf.json"))}
for f in ("EOL", "UFV", "TOTAL"):
    for uf in sorted({r["uf"] for r in sis}):
        rows = [r for r in sis if LTM[0] <= r["mes"] <= LTM[1] and (f == "TOTAL" or r["fonte"] == f) and r["uf"] == uf]
        a = agg(rows)
        if not a["pot"]:
            continue
        uf_12m.append(dict(chave=f"{f}_{uf}", fonte=f, fonte_nome=FONTES[f], uf=uf, estado=NOMES_UF.get(uf, uf),
                           submercado=rows[0]["sub"], potencial_gwh=r1(a["pot"] / 1e3, 1),
                           cortado_gwh=r1(a["cut"] / 1e3, 1), **pcts(a)))

write("sin_mensal", sin_mensal)
write("sistema_12m", sistema_12m)
write("uf_12m", uf_12m)
