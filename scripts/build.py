"""Curtailment (constrained-off) control for 3 complexes, from ONS Dados Abertos.

Usage: python3 -I build.py <data_dir> <out_json>
"""
import json
import sys

import duckdb

DATA, OUT = sys.argv[1], sys.argv[2]
c = duckdb.connect()

c.sql(f"""
create table t as
select *, 'EOL' fonte from read_parquet('{DATA}/eol/*.parquet', union_by_name=true)
union all by name
select *, 'UFV' fonte from read_parquet('{DATA}/sol/*.parquet', union_by_name=true)
""")
c.sql(f"create view d as select * from read_parquet('{DATA}/det/*.parquet', union_by_name=true)")

# Drop implausible SCADA spikes in verified generation (>1.3x the entity's max availability / p99.9).
c.sql("""
create table lim as select id_ons, greatest(max(val_disponibilidade), quantile_cont(val_geracao, 0.999)) * 1.3 lim
from t group by 1
""")
outl = c.sql("select count(*), round(sum(val_geracao)/2/1e3,1) from t join lim using(id_ons) where val_geracao > lim").fetchall()[0]
c.sql("""
create table tc as
select t.* replace (case when val_geracao > lim then null else val_geracao end as val_geracao),
       coalesce(val_geracaonaorealizadaapurada, 0) cut,
       date_trunc('month', din_instante)::date mes
from t join lim using(id_ons)
""")

# Complexes: usinas (CEG-level) and the ONS conjunto(s) they sit in.
TUPI = {
    "icarai": ("Icaraí (Tupi)", ["CEUEIU", "CEUEID"]),
    "taiba": ("Taíba (Tupi)", ["CEUEAG", "CEUEAD", "CEUECL"]),
    "amontada": ("Amontada (Tupi)", ["CEUEIG", "CEUERB", "CEUEBC"]),
    "riachao": ("Riachão (Tupi)", ["RNUER1", "RNUER2", "RNUER4", "RNUER6", "RNUER7"]),
}
COMPLEXES = {
    "assurua": dict(nome="Assuruá 4 e 5 (Serena)", fonte="EOL", sub="NE",
                    usinas=[f"BAEA4{i}" for i in range(1, 7)] + [f"BAEA5{i}" for i in range(1, 7)]),
    "luizcarlos": dict(nome="Luiz Carlos (Atlas)", fonte="UFV", sub="SE",
                       usinas=[f"MGBS{i:02d}" for i in range(9, 18)]),
    "serido": dict(nome="Serra do Seridó (EDF)", fonte="EOL", sub="NE",
                   usinas=["PBSS10", "PBSS11", "PBSS12", "PBSS14", "PBSS16", "PBSS17"]),
    "mirante": dict(nome="Oeste Seridó / Mirante (Elera)", fonte="EOL", sub="NE",
                    usinas=[f"RNOS{i:02d}" for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12)]),
    **{k: dict(nome=n, fonte="EOL", sub="NE", usinas=u, pai="tupi") for k, (n, u) in TUPI.items()},
    "tupi": dict(nome="Tupi consolidado (Ibitu)", fonte="EOL", sub="NE",
                 usinas=[u for _, us in TUPI.values() for u in us]),
}

out = {"meta": {}, "complexos": {}, "bench": {}, "peers": {}, "mapa": []}

# Per-usina monthly bias of ONS estimated vs verified generation in unrestricted half-hours.
# Dividing the estimate by it keeps a usina with an optimistic estimate from taking more of the conjunto's cut.
c.sql("""
create table bias as
select id_ons, date_trunc('month', din_instante) mes,
  case when sum(val_geracaoverificada) filter (where flg_geracaorestrita=0) > 100
       then least(greatest(sum(val_geracaoestimada) filter (where flg_geracaorestrita=0)
                           / sum(val_geracaoverificada) filter (where flg_geracaorestrita=0), 0.5), 2.0)
       else 1.0 end b
from d group by 1, 2
""")
c.sql("""
create view db as
select d.*, greatest(d.val_geracaoestimada / coalesce(bias.b, 1.0) - d.val_geracaoverificada, 0) pc
from d left join bias on bias.id_ons = d.id_ons and bias.mes = date_trunc('month', d.din_instante)
""")

for key, cx in COMPLEXES.items():
    ids = ",".join(f"'{u}'" for u in cx["usinas"])
    # Share of each conjunto-half-hour that belongs to the target usinas:
    #  - generation: share of verified generation (detail file)
    #  - curtailment: share of positive (bias-corrected estimated - verified) on restricted usinas
    c.sql(f"""
    create or replace table sh as
    select id_ons_conjuntousina cj, din_instante,
      sum(case when id_ons in ({ids}) then val_geracaoverificada else 0 end) ger_alvo,
      sum(val_geracaoverificada) ger_tot,
      sum(case when id_ons in ({ids}) and flg_geracaorestrita=1 then pc else 0 end) pc_alvo,
      sum(case when flg_geracaorestrita=1 then pc else 0 end) pc_tot,
      count(*) filter (where id_ons in ({ids})) n_alvo, count(*) n_tot
    from db where id_ons_conjuntousina in (select distinct id_ons_conjuntousina from d where id_ons in ({ids}))
    group by 1,2 having n_alvo > 0
    """)
    cjs = [r[0] for r in c.sql("select distinct cj from sh").fetchall()]
    alloc = """case when sh.n_alvo=sh.n_tot then tc.cut
               when sh.pc_tot>0 then tc.cut*sh.pc_alvo/sh.pc_tot else 0 end"""
    rows = c.sql(f"""
    select tc.mes,
      sum(case when sh.n_alvo=sh.n_tot then tc.val_geracao
               when sh.ger_tot>0 then tc.val_geracao*sh.ger_alvo/sh.ger_tot else 0 end)/2 ger,
      sum({alloc} * (cod_razaorestricao='ENE')::int)/2 ene,
      sum({alloc} * (cod_razaorestricao='CNF')::int)/2 cnf,
      sum({alloc} * (cod_razaorestricao='REL')::int)/2 rel,
      sum({alloc} * (cod_razaorestricao='PAR')::int)/2 par,
      max(sh.n_alvo) n_usinas,
      sum({alloc} * (cod_origemrestricao='LOC')::int)/2 loc
    from tc join sh on tc.id_ons=sh.cj and tc.din_instante=sh.din_instante
    group by 1 order by 1
    """).fetchall()
    out["complexos"][key] = dict(nome=cx["nome"], fonte=cx["fonte"], sub=cx["sub"], conjuntos=cjs, pai=cx.get("pai", ""),
                                 serie=[dict(mes=str(r[0]), ger=r[1], ene=r[2] or 0, cnf=r[3] or 0, rel=r[4] or 0,
                                             par=r[5] or 0, n=r[6], loc=r[7] or 0) for r in rows])
    if key == "tupi":
        continue
    out["mapa"] += [dict(complexo=cx["nome"], **dict(zip(["usina", "id_ons", "ceg", "conjunto", "id_conjunto", "inicio", "fim"], r)))
                    for r in c.sql(f"""select nom_usina, id_ons, ceg, nom_conjuntousina, id_ons_conjuntousina,
                                        min(din_instante)::date::varchar, max(din_instante)::date::varchar
                                        from d where id_ons in ({ids}) group by all order by 2, 6""").fetchall()]

# Last complete month: the month of the last half-hour counts only if that half-hour is 23:30 of its last day.
last = c.sql("select max(din_instante) from t").fetchall()[0][0]
partial = (last + __import__("datetime").timedelta(minutes=30)).month == last.month
fim = c.sql(f"select (date_trunc('month', timestamp '{last}') - interval {1 if partial else 0} month)::date").fetchall()[0][0]
ini = c.sql(f"select (date '{fim}' - interval 11 month)::date").fetchall()[0][0]

excl = {cj for cx in out["complexos"].values() for cj in cx["conjuntos"]}
excl_sql = ",".join(f"'{e}'" for e in excl)

BENCH = {
    "EOL_SIN": "fonte='EOL'", "EOL_NE": "fonte='EOL' and id_subsistema='NE'",
    "UFV_SIN": "fonte='UFV'", "UFV_SE": "fonte='UFV' and id_subsistema='SE'",
    "NE_ALL": "id_subsistema='NE' and mes>='2024-04-01'", "SE_ALL": "id_subsistema='SE' and mes>='2024-04-01'",
}
for k, w in BENCH.items():
    rows = c.sql(f"""select mes, sum(val_geracao)/2,
        sum(cut*(cod_razaorestricao='ENE')::int)/2, sum(cut*(cod_razaorestricao='CNF')::int)/2,
        sum(cut*(cod_razaorestricao='REL')::int)/2, sum(cut*(cod_razaorestricao='PAR')::int)/2,
        count(distinct id_ons), sum(cut*(cod_origemrestricao='LOC')::int)/2
        from tc where {w} and id_ons not in ({excl_sql}) group by 1 order by 1""").fetchall()
    out["bench"][k] = [dict(mes=str(r[0]), ger=r[1], ene=r[2] or 0, cnf=r[3] or 0, rel=r[4] or 0, par=r[5] or 0, n=r[6], loc=r[7] or 0)
                       for r in rows]

# System-wide view (everything ONS publishes, assets included): month x source x submarket x state.
out["sistema"] = [dict(mes=str(r[0]), fonte=r[1], sub=r[2], uf=r[3], ger=r[4] or 0, ene=r[5] or 0, cnf=r[6] or 0,
                       rel=r[7] or 0, par=r[8] or 0, loc=r[9] or 0, n=r[10])
                  for r in c.sql("""select mes, fonte, id_subsistema, id_estado, sum(val_geracao)/2,
        sum(cut*(cod_razaorestricao='ENE')::int)/2, sum(cut*(cod_razaorestricao='CNF')::int)/2,
        sum(cut*(cod_razaorestricao='REL')::int)/2, sum(cut*(cod_razaorestricao='PAR')::int)/2,
        sum(cut*(cod_origemrestricao='LOC')::int)/2, count(distinct id_ons)
        from tc group by all order by all""").fetchall()]

# Peer distribution: last-12-complete-months % cut per conjunto/usina of same fonte+subsistema.
for k, (f, s) in {"EOL_NE": ("EOL", "NE"), "UFV_SE": ("UFV", "SE")}.items():
    rows = c.sql(f"""select id_ons, any_value(nom_usina), any_value(id_estado),
        sum(val_geracao)/2 ger, sum(cut)/2 cut, sum(cut*(cod_razaorestricao='ENE')::int)/2 ene
        from tc where fonte='{f}' and id_subsistema='{s}' and mes between '{ini}' and '{fim}'
        group by 1 having sum(val_geracao)/2 > 50000 order by 1""").fetchall()
    out["peers"][k] = [dict(id=r[0], nome=r[1], uf=r[2], ger=r[3], cut=r[4], ene=r[5]) for r in rows]

out["meta"] = dict(
    outliers=dict(meias_horas=outl[0], gwh=outl[1]),
    ultimo_instante=str(last),
    ltm=dict(ini=str(ini), fim=str(fim), parcial=str(last.date().replace(day=1)) if partial else ""),
    inicio=dict(EOL=str(c.sql("select min(mes) from tc where fonte='EOL'").fetchall()[0][0]),
                UFV=str(c.sql("select min(mes) from tc where fonte='UFV'").fetchall()[0][0])),
    excluidos_bench=sorted(excl),
)
json.dump(out, open(OUT, "w"), ensure_ascii=False, default=float)
print(json.dumps(out["meta"], ensure_ascii=False))
for k, v in out["complexos"].items():
    print(k, v["conjuntos"], len(v["serie"]))
