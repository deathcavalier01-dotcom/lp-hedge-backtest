import streamlit as st
import pandas as pd
from datetime import datetime, timezone

import backtest_eth_FREEZE_20260108 as bt

st.set_page_config(page_title="ETH LP 对冲回测", layout="wide")

st.title("ETH LP 对冲回测（冻结版）")
st.caption("只读调用 backtest_eth_FREEZE_20260108.py，不修改冻结文件。")

# -------- Sidebar inputs --------
with st.sidebar:
    st.header("参数")
    csv_file = st.text_input("CSV_FILE", value="eth_1h.csv")
    start_ts_str = st.text_input("START_TS (ISO, UTC)", value="2025-11-07T00:00:00+00:00")
    end_ts_str = st.text_input("END_TS (ISO, UTC)", value="2026-01-06T00:00:00+00:00")

    Pl = st.number_input("Pl (下界)", value=2651.0, step=1.0, format="%.2f")
    Pu = st.number_input("Pu (上界)", value=3498.0, step=1.0, format="%.2f")

    eth_in_pool = st.number_input("ETH_IN_POOL", value=1.0, step=0.1, format="%.4f")
    hedge_k0 = st.number_input("HEDGE_K0", value=0.7, step=0.05, format="%.4f")
    threshold = st.number_input("THRESHOLD", value=0.05, step=0.01, format="%.4f")

    st.divider()
    run_btn = st.button("运行回测", type="primary")


def parse_iso_utc(s: str) -> datetime:
    # 允许你输入带 +00:00 的 ISO 字符串
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# -------- Run + persist result --------
if run_btn:
    try:
        start_ts = parse_iso_utc(start_ts_str)
        end_ts = parse_iso_utc(end_ts_str)
    except Exception as e:
        st.error(f"时间格式不对：{e}")
        st.stop()

    with st.spinner("回测运行中..."):
        result = bt.run_backtest(
            csv_file=csv_file,
            start_ts=start_ts,
            end_ts=end_ts,
            Pl=Pl,
            Pu=Pu,
            eth_in_pool=eth_in_pool,
            hedge_k0=hedge_k0,
            threshold=threshold,
        )
    st.session_state["last_result"] = result
    st.success("回测完成 ✅")

# -------- Render last result --------
result = st.session_state.get("last_result")
if not result:
    st.info("左侧设置参数，点击【运行回测】开始。")
    st.stop()

summary = result["summary"]
events = result["rebalance_events"]

st.subheader("回测摘要")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total PnL", f"${summary['total_pnl']:.2f}")
c2.metric("Hedge PnL (MTM)", f"${summary['hedge_pnl']:.2f}")
c3.metric("LP PnL (no fees)", f"${summary['lp_pnl']:.2f}")
c4.metric("Rebalances", int(summary["rebalance_count"]))

c5, c6, c7, c8 = st.columns(4)
c5.metric("Final Price", f"${summary['final_price']:.2f}")
c6.metric("Final Hedge Pos", f"{summary['final_hedge_position']:.4f} ETH")
c7.metric("Threshold", f"{summary['threshold']:.4f}")
c8.metric("k0", f"{summary['hedge_k0']:.4f}")

with st.expander("配置回显（本次 run_backtest 实际使用）", expanded=False):
    st.json({
        "CSV_FILE": csv_file,
        "START_TS": start_ts_str,
        "END_TS": end_ts_str,
        "Pl": summary["Pl"],
        "Pu": summary["Pu"],
        "ETH_IN_POOL": summary["eth_in_pool"],
        "HEDGE_K0": summary["hedge_k0"],
        "THRESHOLD": summary["threshold"],
        "P0_used": summary["P0"],
    })

st.subheader("Rebalance 事件")
if events:
    df = pd.DataFrame(events)
    st.dataframe(df, use_container_width=True, height=420)
else:
    st.warning("没有触发 rebalance（events 为空）")

