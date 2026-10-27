"""Compare findings against the planted errors in labels.csv.

Precision: of everything the tool flagged, how much was really planted.
Recall: of everything planted, how much the tool found.
Holdout recall is shown on its own because those variants were not used
while tuning the rules.
"""
import pandas as pd


def _pair(a, b):
    return "|".join(sorted((str(a), str(b))))


def predicted_keys(findings, rule):
    f = findings[findings["rule"] == rule]
    if rule == "R01":
        return {(o, _pair(k, r)) for o, k, r in zip(f["object"], f["key"], f["related"])}
    return set(zip(f["object"], f["key"]))


def labeled(labels, rule):
    l = labels[labels["rule"] == rule]
    if rule == "R01":
        l = l.assign(key=[_pair(*k.split("|")) for k in l["key"]])
    return l


def evaluate(findings, labels):
    rows, misses, extras = [], [], []
    for rule in sorted(labels["rule"].unique()):
        lab = labeled(labels, rule)
        truth = set(zip(lab["object"], lab["key"]))
        pred = predicted_keys(findings, rule)
        tp, fp, fn = truth & pred, pred - truth, truth - pred
        hold = lab[lab["holdout"] == "X"]
        hold_keys = set(zip(hold["object"], hold["key"]))
        rows.append({
            "rule": rule,
            "planted": len(truth),
            "flagged": len(pred),
            "found": len(tp),
            "false_pos": len(fp),
            "precision": round(len(tp) / len(pred), 3) if pred else None,
            "recall": round(len(tp) / len(truth), 3) if truth else None,
            "holdout_recall": round(len(hold_keys & pred) / len(hold_keys), 3) if hold_keys else None,
        })
        for _, r in lab.iterrows():
            if (r["object"], r["key"]) in fn:
                misses.append({"rule": rule, "object": r["object"], "key": r["key"],
                               "variant": r["variant"], "holdout": r["holdout"]})
        for o, k in sorted(fp):
            extras.append({"rule": rule, "object": o, "key": k})
    return pd.DataFrame(rows), pd.DataFrame(misses), pd.DataFrame(extras)


def to_markdown(df):
    if df.empty:
        return "(none)\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(lines) + "\n"
