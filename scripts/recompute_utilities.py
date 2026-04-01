"""
recompute all 18 condition utilities from audit logs using corrected prices.

corrections applied vs original metrics:
- Q5103: $612.15 -> $599.70/infusion (verified WV BMS ASP file)
- 96413: $130.00 -> $133.27 (verified CMS PFS 2026 non-facility)
- 96365: $70.00  -> $67.14  (verified CMS PFS 2026 non-facility)
- 74183: $350.00 -> $336.01 (verified CMS PFS 2026 non-facility)
- 72197: $350.00 -> $334.34 (verified CMS PFS 2026 non-facility)
- admin costs: flat $5.79/$0.05 -> level-differentiated
  (L0: $5.79/$0.05, L1-2: $10.97/$3.52 per CAQH 2023)
- IRE cost: $650 (Sanjay) + prompt-pay interest (4.125%, 67 days) when L2 reached + overturn
- prompt-pay rate: 4.875% -> 4.125% (H1 2026 Bureau of Fiscal Service)
- review timeline: 74 days -> 67 days (per CMS-4208-F effective 2026-01-01)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.pricing.cms_rates import (
    lookup_rate, UnknownProcedureCodeError,
    ADMIN_COST_PROVIDER_L0, ADMIN_COST_INSURER_L0,
    ADMIN_COST_PROVIDER_L12, ADMIN_COST_INSURER_L12,
    IRE_CASE_COST, PROMPT_PAY_RATE, REVIEW_DELAY_DAYS,
)

ASYM_DIR = ROOT / "outputs" / "asym_experiments_1333"
SYM_DIR  = ROOT / "outputs" / "experiments_4587"

CONDITIONS = ["CP_CI", "CP_DI", "CP_NI", "DP_CI", "DP_DI", "DP_NI", "NP_CI", "NP_DI", "NP_NI"]


def find_audit(directory: Path, condition: str) -> Path:
    matches = list(directory.glob(f"*_{condition}_*_audit.json"))
    if not matches:
        raise FileNotFoundError(f"no audit file for {condition} in {directory}")
    return matches[0]


def count_turns_by_level(events: list) -> dict:
    """
    infer phase2 turns at each level from the sequence of response_built and
    phase2_appeal_advanced events.

    logic: each response_built in phase_2 = 1 turn. the level of that turn is
    determined by the current level at the time of the response, which starts at 0
    and advances when phase2_appeal_advanced events fire (at end of the same turn).
    we assign the level BEFORE any appeal events on that turn.
    """
    level_counts = {}
    current_level = 0
    last_response_turn = None

    for e in events:
        if e.get("phase") != "phase_2_utilization_review":
            continue
        kind = e.get("kind", "")
        turn = e.get("turn", 0)

        if kind == "response_built":
            last_response_turn = turn
            level_counts[current_level] = level_counts.get(current_level, 0) + 1

        elif kind == "phase2_appeal_advanced":
            to_level = e["payload"].get("to_level", current_level)
            current_level = max(current_level, to_level)

    return level_counts


def recompute(audit_path: Path, info_condition: str, condition: str) -> dict:
    with open(audit_path) as f:
        data = json.load(f)
    events = data["events"]

    # get summary metrics from the metrics_calculated event
    base_metrics = {}
    for e in reversed(events):
        if e.get("kind") == "metrics_calculated":
            base_metrics = e["payload"]["metrics"]
            break

    phase2_turns = base_metrics.get("phase2_turns", 0)
    phase3_turns = base_metrics.get("phase3_turns", 0)
    max_level = base_metrics.get("max_appeal_level_reached", 0)
    line_pricing = base_metrics.get("line_pricing", [])

    # build approved_quantity map from audit events (ground truth for modified lines)
    # use the last phase2_line_adjudicated event per line — this is the authoritative approved_quantity
    approved_qty_map = {}
    for e in events:
        if e.get("kind") == "phase2_line_adjudicated":
            p = e.get("payload", {})
            ln = p.get("line_number")
            new = p.get("new", {})
            aq = new.get("approved_quantity")
            if aq is not None:
                approved_qty_map[ln] = aq

    # count turns by level from response_built events
    level_counts = count_turns_by_level(events)
    n_l0  = level_counts.get(0, 0)
    n_l12 = sum(v for k, v in level_counts.items() if k > 0)

    # sanity check: level_counts total should match phase2_turns
    if sum(level_counts.values()) != phase2_turns:
        # fallback: trust phase2_turns from metrics, assume difference is at L0
        deficit = phase2_turns - sum(level_counts.values())
        level_counts[0] = level_counts.get(0, 0) + deficit

    # admin costs: level-differentiated
    admin_p = (n_l0 + phase3_turns) * ADMIN_COST_PROVIDER_L0 + n_l12 * ADMIN_COST_PROVIDER_L12
    admin_i = (n_l0 + phase3_turns) * ADMIN_COST_INSURER_L0  + n_l12 * ADMIN_COST_INSURER_L12

    # recompute service values using corrected rates (ignore stored rate in line_pricing)
    # for paid lines: use approved_quantity from audit (handles modified lines correctly)
    R_P = 0.0
    S_I = 0.0
    unpriced = []
    repriced = []

    for lp in line_pricing:
        code = lp.get("procedure_code", "")
        req_qty = lp.get("requested_quantity", 0)
        line_num = lp.get("line_number")
        paid = lp.get("paid", False)

        # approved_quantity: from audit map (authoritative), else requested_quantity
        approved_qty = approved_qty_map.get(line_num, req_qty) if paid else req_qty

        try:
            rate = lookup_rate(code)
        except UnknownProcedureCodeError:
            unpriced.append(code)
            rate = lp.get("rate")  # fall back to stored rate if unknown

        sv = (rate * req_qty) if rate and req_qty > 0 else 0.0
        pv = (rate * approved_qty) if rate and paid and approved_qty > 0 else 0.0

        S_I += sv
        R_P += pv
        repriced.append({
            "code": code, "req_qty": req_qty, "approved_qty": approved_qty, "rate": rate,
            "sv": round(sv, 2), "paid": paid, "pv": round(pv, 2),
            "old_rate": lp.get("rate"),
        })

    # IRE reversal costs: F_IRE + prompt-pay interest when L2 reached and overturn occurred
    ire_cost = 0.0
    interest = 0.0
    if max_level >= 2:
        ire_cost += IRE_CASE_COST
        if R_P > 0:
            interest = PROMPT_PAY_RATE * R_P * REVIEW_DELAY_DAYS / 365
            ire_cost += interest

    U_P = R_P - admin_p
    U_I = S_I - R_P - admin_i - ire_cost

    return {
        "condition": condition,
        "info": info_condition,
        "max_level": max_level,
        "phase2_turns": phase2_turns,
        "level_counts": level_counts,
        "n_l0": n_l0, "n_l12": n_l12,
        "phase3_turns": phase3_turns,
        "admin_p": round(admin_p, 2),
        "admin_i": round(admin_i, 2),
        "ire_cost": round(ire_cost, 2),
        "interest": round(interest, 2),
        "S_I": round(S_I, 2),
        "R_P": round(R_P, 2),
        "U_P": round(U_P, 2),
        "U_I": round(U_I, 2),
        "repriced_lines": repriced,
        "unpriced": unpriced,
    }


def main():
    results = []

    print(f"\n{'='*100}")
    print(f"{'COND':<8} {'INFO':<5} {'P2':>3} {'L0':>4} {'L12':>4} {'P3':>3} {'LVL':>4} "
          f"{'S_I':>10} {'R_P':>10} {'C_P':>7} {'C_I':>7} {'IRE':>7} {'INT':>6} {'U_P':>10} {'U_I':>10}")
    print(f"{'-'*100}")

    for cond in CONDITIONS:
        for directory, info in [(SYM_DIR, "sym"), (ASYM_DIR, "asym")]:
            try:
                audit_path = find_audit(directory, cond)
                r = recompute(audit_path, info, cond)
                results.append(r)
                flag = " ⚠" if r["unpriced"] else ""
                print(f"{r['condition']:<8} {r['info']:<5} {r['phase2_turns']:>3} {r['n_l0']:>4} "
                      f"{r['n_l12']:>4} {r['phase3_turns']:>3} {r['max_level']:>4} "
                      f"{r['S_I']:>10.2f} {r['R_P']:>10.2f} {r['admin_p']:>7.2f} "
                      f"{r['admin_i']:>7.2f} {r['ire_cost']:>7.2f} {r['interest']:>6.2f} "
                      f"{r['U_P']:>10.2f} {r['U_I']:>10.2f}{flag}")
                if r["unpriced"]:
                    print(f"  ⚠ unpriced: {r['unpriced']}")
            except FileNotFoundError as e:
                print(f"  MISSING: {e}")

    print(f"{'='*100}")

    # 2x2 payoff matrices
    asym = {r["condition"]: r for r in results if r["info"] == "asym"}
    sym  = {r["condition"]: r for r in results if r["info"] == "sym"}

    for label, matrix in [("SYMMETRIC", sym), ("ASYMMETRIC", asym)]:
        pure = {c: matrix[c] for c in ["CP_CI", "CP_DI", "DP_CI", "DP_DI"] if c in matrix}
        if len(pure) == 4:
            print(f"\n{label} 2x2 PAYOFF MATRIX (U_P, U_I):")
            print(f"{'':20} {'Insurer C':>22} {'Insurer D':>22}")
            cp = pure["CP_CI"]; cd = pure["CP_DI"]
            dp = pure["DP_CI"]; dd = pure["DP_DI"]
            print(f"{'Provider C':20} ({cp['U_P']:>8.2f}; {cp['U_I']:>8.2f})     ({cd['U_P']:>8.2f}; {cd['U_I']:>8.2f})")
            print(f"{'Provider D':20} ({dp['U_P']:>8.2f}; {dp['U_I']:>8.2f})     ({dd['U_P']:>8.2f}; {dd['U_I']:>8.2f})")

    out_path = ROOT / "outputs" / "recomputed_utilities.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nfull results saved to {out_path}")


if __name__ == "__main__":
    main()
