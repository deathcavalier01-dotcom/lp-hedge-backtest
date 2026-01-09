# STABLE CONFIG — validated with backtest_eth_FREEZE_20260108.py
# Changing this file invalidates historical results

# config.py
# All strategy parameters live here. backtest_eth.py should not hardcode numbers.

# ===== Data =====
CSV_FILE = "eth_1h.csv"
START_TS = "2025-11-07T00:00:00+00:00"
END_TS   = "2026-01-06T00:00:00+00:00"
P0_MODE = "from_data"   # "from_data" or "fixed"

# ===== LP init (ETH must fill) =====
# NOTE:
# P0 here is only a fallback / UI display value.
# Actual P0 used in backtest is decided by P0_MODE.
P0 = 3150.0
PL = 2651.0
PU = 3498.0
ETH_IN_POOL = 1.0

# ===== Hedge =====
HEDGE_K0 = 0.7
THRESHOLD = 0.05  # 5% trigger

