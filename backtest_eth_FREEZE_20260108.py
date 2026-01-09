"""
Historical backtest of delta-neutral LP hedging strategy on ETH (Uniswap v3 style math).
Frictionless simulation: no fees, no slippage, no funding costs.

Data: ETH 1h CSV (default: eth_1h.csv)
"""

import csv
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

from v3_math import lp_value, amounts_from_L
from init_position import calc_usdt_for_eth_in_pool

import config as cfg


# -----------------------------
# Helpers: time parsing
# -----------------------------
def _parse_ts_any(ts_raw: str) -> datetime:
    s = (ts_raw or "").strip()

    # 1) ISO (with or without timezone)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        pass

    # 2) epoch seconds/ms/us/ns
    x = float(s)
    ax = abs(x)
    if ax >= 1e18:
        sec = x / 1e9      # ns
    elif ax >= 1e15:
        sec = x / 1e6      # us
    elif ax >= 1e12:
        sec = x / 1e3      # ms
    else:
        sec = x            # seconds
    return datetime.fromtimestamp(sec, tz=timezone.utc)


def _pick_col(fieldnames: List[str], candidates: List[str]) -> str:
    norm = {fn.strip().lower(): fn for fn in fieldnames if fn is not None}
    for c in candidates:
        if c in norm:
            return norm[c]
    raise ValueError(f"Cannot find columns {candidates} in {fieldnames}")


def load_eth_1h_csv(filename: str) -> List[Tuple[datetime, float]]:
    """
    Load ETH 1h close data from CSV.

    Supports timestamp columns:
      - timestamp / open_time / time / date
      - open_time_ms / open_time (binance style)

    Supports close columns:
      - close (tolerates trailing spaces)
    """
    rows: List[Tuple[datetime, float]] = []
    with open(filename, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no headers")

        ts_col = _pick_col(
            reader.fieldnames,
            ["timestamp", "open_time", "open_time_ms", "time", "date"]
        )
        close_col = _pick_col(reader.fieldnames, ["close", "close "])

        for row in reader:
            ts_raw = row.get(ts_col, "")
            close_raw = row.get(close_col, "")
            dt = _parse_ts_any(str(ts_raw))
            px = float(str(close_raw).strip())
            rows.append((dt, px))

    if not rows:
        raise ValueError(f"No rows loaded from {filename}")

    rows.sort(key=lambda x: x[0])
    return rows


def filter_period(
    data: List[Tuple[datetime, float]],
    start_ts: datetime,
    end_ts: datetime,
) -> List[Tuple[datetime, float]]:
    out: List[Tuple[datetime, float]] = []
    for ts, p in data:
        if start_ts <= ts <= end_ts:
            out.append((ts, p))
    return out


# -----------------------------
# Strategy rule: k(P)
# -----------------------------
def calculate_k(P: float, Pl: float, Pu: float, k0: float) -> float:
    """
    Piecewise linear hedge ratio k(P):
    - At Plower: k = 1.0
    - At midpoint: k = k0
    - At Pupper: k = 0.0
    """
    if P <= Pl:
        return 1.0
    if P >= Pu:
        return 0.0

    mid = (Pl + Pu) / 2.0
    if P <= mid:
        # 1.0 -> k0
        return 1.0 - (1.0 - k0) * (P - Pl) / (mid - Pl)
    else:
        # k0 -> 0.0
        return k0 - k0 * (P - mid) / (Pu - mid)


# -----------------------------
# Backtest core
# -----------------------------
def run_backtest(
    csv_file: Optional[str] = None,
    start_ts: Optional[datetime] = None,
    end_ts: Optional[datetime] = None,
    Pl: Optional[float] = None,
    Pu: Optional[float] = None,
    eth_in_pool: Optional[float] = None,
    hedge_k0: Optional[float] = None,
    threshold: Optional[float] = None,
) -> Dict:
    # ---- load config defaults ----
    csv_file = csv_file or cfg.CSV_FILE
    start_ts = start_ts or datetime.fromisoformat(cfg.START_TS)
    end_ts = end_ts or datetime.fromisoformat(cfg.END_TS)

    if start_ts.tzinfo is None:
        start_ts = start_ts.replace(tzinfo=timezone.utc)
    else:
        start_ts = start_ts.astimezone(timezone.utc)

    if end_ts.tzinfo is None:
        end_ts = end_ts.replace(tzinfo=timezone.utc)
    else:
        end_ts = end_ts.astimezone(timezone.utc)

    Pl = float(Pl if Pl is not None else cfg.PL)
    Pu = float(Pu if Pu is not None else cfg.PU)
    eth_in_pool = float(eth_in_pool if eth_in_pool is not None else cfg.ETH_IN_POOL)
    hedge_k0 = float(hedge_k0 if hedge_k0 is not None else cfg.HEDGE_K0)
    threshold = float(threshold if threshold is not None else cfg.THRESHOLD)

    # ---- Load + filter data ----
    data_all = load_eth_1h_csv(csv_file)
    price_data = filter_period(data_all, start_ts, end_ts)
    if len(price_data) < 2:
        raise ValueError(f"Not enough data points in period. got={len(price_data)}")

    # ---- Decide P0 ----
    if getattr(cfg, "P0_MODE", "fixed") == "from_data":
        P0 = float(price_data[0][1])
    else:
        P0 = float(cfg.P0)

    # ---- ETH-must-fill init: derive initial_usdt and L from ETH amount ----
    initial_usdt = calc_usdt_for_eth_in_pool(P0, Pl, Pu, eth_in_pool)

    import math
    sqrtP = math.sqrt(P0)
    sqrtPu = math.sqrt(Pu)
    denom = (1.0 / sqrtP) - (1.0 / sqrtPu)
    if denom <= 0:
        raise ValueError("Invalid range: need P0 < Pu and positive denom for L")
    L = eth_in_pool / denom
    eth0, usdt0 = amounts_from_L(P0, Pl, Pu, L)
    print("DEBUG amounts@P0:", eth0, usdt0)

    # ---- initial hedge ----
    initial_short_eth = eth_in_pool * hedge_k0
    current_H = -initial_short_eth  # short is negative
    cash = 0.0
    cash += initial_short_eth * P0

    # ---- Backtest state ----
    anchor_price = P0
    rebalance_events: List[Dict] = []
    rebalance_count = 0
    cumulative_abs_delta_h = 0.0

    # Hedge bookkeeping (cash + position, mark-to-market at the end)

    # LP value start
    lp_value_start = lp_value(P0, Pl, Pu, L)

    # ---- Print config ----
    print("\n=== Backtest Configuration ===")
    print(f"CSV: {csv_file}")
    print(f"Period: {start_ts.isoformat()} to {end_ts.isoformat()}")
    print(f"Total hours: {len(price_data)}")
    print(f"P0: {P0:.2f}, Range: [{Pl:.2f}, {Pu:.2f}]")
    print(f"Initial LP value: ${lp_value_start:.2f}")
    print(f"Initial hedge: {current_H:.4f} ETH")
    print(f"Liquidity L: {L:.2f}")

    # ---- Iterate over data ----
    for i in range(1, len(price_data)):
        ts, P_now = price_data[i]

        # Trigger: |P - anchor| / anchor >= threshold
        move = abs(P_now - anchor_price) / anchor_price
        if move < threshold:
            continue

        # BEFORE state
        H_before = current_H

        # compute target hedge based on k(P)
        k = calculate_k(P_now, Pl, Pu, hedge_k0)

        # LP composition at P_now (so hedge is based on current ETH in LP)
        # ⚠️ 注意：amounts_from_L 返回顺序必须是 (eth, usdt)。如果你 v3_math 里相反，这里要对调。
        eth_now, usdt_now = amounts_from_L(P_now, Pl, Pu, L)

        target_H = -(eth_now * k)
        delta_h = target_H - H_before
        cumulative_abs_delta_h += abs(delta_h)

        # Execute trade at P_now: cash decreases by delta_h * price
        # 例：delta_h = +0.2（回补空单买入0.2ETH）=> cash -= 0.2*P（现金减少）
        cash -= delta_h * P_now
        current_H = target_H

        # Mark-to-market hedge pnl at this moment
        hedge_pnl_mtm = cash + current_H * P_now

        rebalance_count += 1
        rebalance_events.append({
            "ts": ts.isoformat(),
            "price": P_now,
            "anchor_before": anchor_price,
            "move": move,
            "k": k,
            "eth_now": eth_now,
            "H_before": H_before,
            "H_target": target_H,
            "delta_H": delta_h,
            "cash": cash,
            "hedge_pnl_mtm": hedge_pnl_mtm,
        })

        # update anchor only after rebalance
        anchor_price = P_now

    final_price = float(price_data[-1][1])


    # Final mark-to-market for hedge
    hedge_pnl = cash + current_H * final_price

    lp_value_end = lp_value(final_price, Pl, Pu, L)
    lp_pnl = lp_value_end - lp_value_start
    total_pnl = lp_pnl + hedge_pnl

    summary = {
        "rebalance_count": rebalance_count,
        "cumulative_abs_delta_h": cumulative_abs_delta_h,
        "hedge_pnl": hedge_pnl,
        "lp_pnl": lp_pnl,
        "total_pnl": total_pnl,
        "final_price": final_price,
        "lp_value_start": lp_value_start,
        "lp_value_end": lp_value_end,
        "final_hedge_position": current_H,
        "P0": P0,
        "Pl": Pl,
        "Pu": Pu,
        "L": L,
        "eth_in_pool": eth_in_pool,
        "initial_usdt_required": initial_usdt,
        "threshold": threshold,
        "hedge_k0": hedge_k0,
    }

    return {
        "rebalance_events": rebalance_events,
        "summary": summary,
    }


def write_rebalance_events_csv(events: List[Dict], filename: str = "rebalance_events.csv"):
    if not events:
        print("No rebalance events to write")
        return
    fieldnames = list(events[0].keys())
    with open(filename, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(events)
    print(f"\nWrote {len(events)} events -> {filename}")


def print_summary(summary: Dict):
    print("\n" + "=" * 60)
    print("SUMMARY (frictionless)")
    print("=" * 60)
    print(f"Rebalances: {summary['rebalance_count']}")
    print(f"Cumulative |ΔH|: {summary['cumulative_abs_delta_h']:.4f} ETH")
    print(f"Hedge PnL: ${summary['hedge_pnl']:.2f}")
    print(f"LP PnL (no fees): ${summary['lp_pnl']:.2f}")
    print(f"Total PnL: ${summary['total_pnl']:.2f}")
    print(f"Final price: ${summary['final_price']:.2f}")
    print(f"Final hedge position: {summary['final_hedge_position']:.4f} ETH")
    print(f"LP start/end: ${summary['lp_value_start']:.2f} -> ${summary['lp_value_end']:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    results = run_backtest()

    s = results["summary"]
    print("\n=== Initial Position (ETH-must-fill) ===")
    print(f"price        : {s['P0']:.2f}")
    print(f"range        : [{s['Pl']:.2f}, {s['Pu']:.2f}]")
    print(f"eth_in_pool  : {s['eth_in_pool']:.4f}")
    print(f"usdt_required: {s['initial_usdt_required']:.6f}")
    print("=======================================\n")

    write_rebalance_events_csv(results["rebalance_events"], "rebalance_events.csv")
    print_summary(s)

    print("\n=== Files Generated ===")
    print("- rebalance_events.csv")

