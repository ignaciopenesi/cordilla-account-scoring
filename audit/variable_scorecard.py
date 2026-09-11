"""Variable scorecard + grid validation: is there a better ranking key than the hand-made tiers?

Protocol (leak-free): the 1,099 labelled rows with a closed window, sorted by date. TRAIN = the
older rows, TEST = the newer. Every rate below is estimated on TRAIN only and applied to TEST.
No model is fitted. Two splits (799/300 and 60/40) so a result must hold twice.

Keys compared on TEST, recall@K and hours per buyer:
  A  the hand-made tiers in serving/ (1-4 contacts: trial, then vendor record, then count)
  B  the effort x intent grid, ranked by each cell's TRAIN conversion rate (shrunk toward base, alpha=20)
  C  the same grid ranked by conversions PER CONTACT SPENT in the cell -- "a metric per effort"
  D  the model, out-of-fold          E  random (200 draws)

Result (2026-09-11): A >= B on both splits at K=60 (12 vs 11; 12 vs 11). C is clearly worse
(8 vs 12; 9 vs 12): dividing by contacts spent penalises the accounts that needed calls because
they were converting -- the same confounding as the model, moved into the denominator -- and lets
tiny 5+ cells (n=6-8) float to the top. Restricted to the same universe as A, the grid derives
trial > {none, vendor} > {web, mql at ~2%}: it rediscovers the hand order, and confirms web-only
and MQL-only are noise. The variable scorecard: every column alone is AUC 0.50-0.56.
The current tiers stand. Run: python audit/variable_scorecard.py
"""
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from sklearn.metrics import roc_auc_score
pd.set_option("display.width", 220)
TODAY = pd.Timestamp("2026-08-01")
t = pd.read_csv(__import__("pathlib").Path(__file__).resolve().parent.parent / "data/training_data.csv", parse_dates=["snapshot_date"]); t["p_oof"] = np.load(__import__("pathlib").Path(__file__).resolve().parent / "oof_predictions.npy")
t = t[(TODAY - t.snapshot_date).dt.days >= 90].sort_values("snapshot_date").reset_index(drop=True)

def effort(d): return np.select([d.sales_contacts_90d==0, d.sales_contacts_90d<=4], ["0","1-4"], "5+")
def intent(d): return np.select([d.trial_started==1, d.intent_score.notna(), d.web_touchpoints_90d>=4, d.mql_count_90d>0], ["trial","vendor","web","mql"], "none")
def cells(d): x=d.copy(); x["cell"]=[f"{e}|{i}" for e,i in zip(effort(x),intent(x))]; return x

# ── 1 · VARIABLE SCORECARD, on train only ────────────────────────────────────────────
def scorecard(train):
    y=train.converted_within_90d; rows=[]
    for col in ["sales_contacts_90d","trial_started","trial_active_users","mql_count_90d","web_touchpoints_90d","employee_count","intent_score","p_oof"]:
        x=train[col]; miss=x.isna().mean()
        auc=roc_auc_score(y, x.fillna(x.median())) if x.nunique()>1 else np.nan
        rows.append(dict(variable=col, faltantes=f"{miss:.0%}", AUC=round(auc,3), señal=("sí" if abs(auc-.5)>=.05 else "débil" if abs(auc-.5)>=.02 else "no")))
    cov=train.intent_score.notna(); rows.append(dict(variable="intent_score PRESENTE (cobertura)", faltantes="—", AUC=round(roc_auc_score(y,cov.astype(int)),3), señal="sí"))
    for c in ["account_type","industry"]:
        g=train.groupby(c).converted_within_90d.mean(); rows.append(dict(variable=c, faltantes="—", AUC=np.nan, señal=f"rango {g.min():.1%}–{g.max():.1%} → " + ("no" if g.max()-g.min()<.03 else "algo")))
    return pd.DataFrame(rows)

# ── 2 · RANKING KEYS ──────────────────────────────────────────────────────────────
def keys_from_train(train, alpha=20):
    tr=cells(train); base=tr.converted_within_90d.mean()
    g=tr.groupby("cell").agg(n=("converted_within_90d","size"), k=("converted_within_90d","sum"), contacts=("sales_contacts_90d","sum"))
    g["rate_smooth"]=(g.k+alpha*base)/(g.n+alpha)                       # B: shrunk toward base
    g["per_contact"]=np.where(g.contacts>0, (g.k+alpha*base)/(g.contacts+alpha*max(tr.sales_contacts_90d.mean(),1)), np.nan)  # C: conversions per contact spent, shrunk
    return g, base
def tier_key(d):   # A: current rules
    C=d.sales_contacts_90d; tier=np.select([C.between(1,4)&(d.trial_started==1), C.between(1,4)&d.intent_score.notna(), C.between(1,4)], [3,2,1], 0)
    return tier*100 + np.where(C.between(1,4), C, 0)
def evaluate(train, test, label):
    g, base = keys_from_train(train); te=cells(test); NPOS=int(te.converted_within_90d.sum())
    te["A_tier"]=tier_key(te); te["B_rate"]=te.cell.map(g.rate_smooth).fillna(base); te["C_perc"]=te.cell.map(g.per_contact)
    # C: 0-contact cells have no effort history -> they are explore territory, placed after all contacted cells
    te["C_perc"]=te.C_perc.fillna(-1)
    called = te[te.sales_contacts_90d>0]   # A and C only rank contacted accounts; explore is a quota, judged separately
    print(f"\n══ {label} · test n={len(te)} · {NPOS} compradores · base test {te.converted_within_90d.mean():.1%} ══")
    rows=[]
    for K in (30,60,90):
        r=dict(K=K)
        for name, df, key, asc in (("A escalones actuales", called, ["A_tier","sales_contacts_90d"], [False,False]),
                                   ("B tasa de celda", called, ["B_rate","sales_contacts_90d"], [False,False]),
                                   ("C conv. por contacto (esfuerzo)", called, ["C_perc","sales_contacts_90d"], [False,True]),
                                   ("D modelo OOF", te, ["p_oof"], [False])):
            sel=df.sort_values(key+["account_id"], ascending=asc+[True]).head(K); k=int(sel.converted_within_90d.sum())
            r[name]=f"{k:2d} · {k/NPOS:.0%} · {K*12/60/max(k,1):.1f}h"
        rng=np.random.default_rng(3); rnd=np.mean([te.sample(K,random_state=int(s)).converted_within_90d.sum() for s in rng.integers(0,1e6,200)])
        r["E azar"]=f"{rnd:4.1f} · {rnd/NPOS:.0%}"
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False)); print("  (compradores encontrados · recall · horas por comprador)")
    # the cells, as C sees them
    show=g.assign(rate=g.k/g.n).sort_values("per_contact",ascending=False)[["n","k","rate","per_contact"]]
    show["rate"]=show.rate.map("{:.1%}".format); show["per_contact"]=show.per_contact.map(lambda v: f"{v:.3f}" if pd.notna(v) else "sin esfuerzo (explore)")
    print(f"\n  celdas ordenadas por C (conv. por contacto, suavizado), estimadas en train n={len(train)}:"); print("  "+show.to_string().replace("\n","\n  "))

print("══ 1 · SCORECARD DE VARIABLES — sobre las 799 de train (nada del test) ══")
print(scorecard(t.iloc[:-300]).to_string(index=False))
evaluate(t.iloc[:-300], t.iloc[-300:], "SPLIT 1 · train 799 más viejas → test 300 más nuevas")
cut=int(len(t)*.6); evaluate(t.iloc[:cut], t.iloc[cut:], f"SPLIT 2 · train 60% ({cut}) → test 40% ({len(t)-cut})")
