# sweep_2d.py
import io
import contextlib

import backtest_eth as bt


def run_once(threshold: float, hedge_k0: float) -> dict:
    """
    Run one backtest with given params, without touching global config.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = bt.run_backtest(threshold=threshold, hedge_k0=hedge_k0)
    return res


def main():
    thresholds = [0.03, 0.05, 0.07, 0.10, 0.15]
    hedge_k0s = [0.30, 0.50, 0.70, 0.90]

    print("2D SWEEP: cell = TotalPnL (USD)")
    print(f"{'TH\\K':>8}", end="")
    for k in hedge_k0s:
        print(f"{k:>12.2f}", end="")
    print()
    print("-" * (8 + 12 * len(hedge_k0s)))

    detailed = []

    for th in thresholds:
        print(f"{th:>8.2f}", end="")
        for k0 in hedge_k0s:
            res = run_once(th, k0)
            s = res["summary"]

            total = float(s["total_pnl"])
            hedge = float(s["hedge_pnl"])
            lp = float(s["lp_pnl"])
            reb = int(s["rebalance_count"])
            cum = float(s["cumulative_abs_delta_h"])

            print(f"{total:>12.2f}", end="")

            detailed.append({
                "threshold": th,
                "hedge_k0": k0,
                "total_pnl": total,
                "hedge_pnl": hedge,
                "lp_pnl": lp,
                "rebalances": reb,
                "cum_abs_dh": cum,
            })
        print()

    detailed.sort(key=lambda x: x["total_pnl"], reverse=True)

    print("\nTop 10 (best TotalPnL first):")
    print(f"{'Rank':<5} {'TH':<6} {'K0':<6} {'TotalPnL':<10} {'HedgePnL':<10} {'LPPnL':<10} {'Reb':<5} {'Cum|ΔH|':<10}")
    print("-" * 90)
    for i, d in enumerate(detailed[:10], 1):
        print(
            f"{i:<5} {d['threshold']:<6.2f} {d['hedge_k0']:<6.2f} "
            f"{d['total_pnl']:<10.2f} {d['hedge_pnl']:<10.2f} {d['lp_pnl']:<10.2f} "
            f"{d['rebalances']:<5} {d['cum_abs_dh']:<10.4f}"
        )


if __name__ == "__main__":
    main()

