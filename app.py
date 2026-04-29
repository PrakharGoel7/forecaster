"""Kalshi Forecaster — Streamlit UI."""
import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import streamlit as st
from forecaster.kalshi import KalshiClient, KalshiMarket, _strip_html
from forecaster.config import ForecasterConfig
from forecaster.forecaster_system import ForecasterSystem
from forecaster.models import ForecastMemo
from forecaster import db

st.set_page_config(page_title="Forecaster", page_icon="◈", layout="wide",
                   initial_sidebar_state="expanded", menu_items={})

st.html("""
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif !important; }
.stApp { background: #f7f6f3; }
#MainMenu, footer { visibility: hidden; }
header { visibility: hidden; height: 0 !important; }
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"] { display: none !important; }
section[data-testid="stSidebar"] {
    transform: none !important; min-width: 240px !important; width: 240px !important;
}
.block-container { padding: 2.5rem 2.5rem 4rem !important; max-width: 1400px !important; }

/* Sidebar */
[data-testid="stSidebar"] { background: #151515 !important; }
[data-testid="stSidebar"] * { color: #d4d0ca !important; }
[data-testid="stSidebar"] .stButton > button {
    background: #e36438 !important; color: #fff !important; border: none !important;
    border-radius: 5px !important; font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important; width: 100% !important; padding: 0.55rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover { background: #c4421a !important; }

/* All buttons */
.stButton > button {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    border-radius: 8px !important;
    transition: all 0.15s ease !important;
}

/* Text inputs */
.stTextInput input {
    font-size: 15px !important; padding: 0.75rem 1.1rem !important; border-radius: 10px !important;
    border: 1.5px solid #e3dfd8 !important; background: #fff !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important; color: #1a1a1a !important;
}
.stTextInput input:focus { border-color: #e36438 !important; box-shadow: 0 0 0 3px rgba(227,100,56,0.1) !important; }
.stTextInput input::placeholder { color: #c0bcb6 !important; }
.stTextInput label { display: none !important; }

/* Cards */
[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1.5px solid #eae7e0 !important;
    border-radius: 14px !important;
    background: #fff !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05) !important;
    padding: 4px !important;
}

/* Event cards */
.ev-card { padding: 6px 4px 0; }
.ev-cat {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: #e36438; margin-bottom: 8px;
    font-family: 'JetBrains Mono', monospace;
}
.ev-title { font-size: 15px; font-weight: 650; color: #1a1a1a; line-height: 1.45; margin-bottom: 6px; }
.ev-sub   { font-size: 12px; color: #9b9790; }

/* Forecast history cards */
.fc-card { padding: 6px 4px 4px; }
.fc-q { font-size: 14px; font-weight: 600; color: #1a1a1a; line-height: 1.4; margin: 8px 0 10px; }
.fc-stats { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.fc-prob { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; }
.fc-sep  { color: #d4d0ca; font-size: 11px; }
.fc-mkt  { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #9b9790; }
.fc-edge { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; }
.fc-date { font-size: 11px; color: #b0acA6; font-family: 'JetBrains Mono', monospace; margin-top: 2px; }

/* Stat row (detail view) */
.stat-row { display: flex; gap: 36px; margin: 20px 0 24px; flex-wrap: wrap; }
.stat { display: flex; flex-direction: column; gap: 3px; }
.stat-lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #9b9790; font-family: 'JetBrains Mono', monospace;
}
.stat-val { font-size: 26px; font-weight: 700; font-family: 'JetBrains Mono', monospace; line-height: 1; }
.stat-sub { font-size: 11px; color: #9b9790; margin-top: 2px; }
.p-hi { color: #16a34a; } .p-mid { color: #d97706; } .p-lo { color: #dc2626; }

/* Rules boxes */
.rules-lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #9b9790; margin-bottom: 7px;
    font-family: 'JetBrains Mono', monospace;
}
.rules-box {
    background: #f7f6f3; border: 1px solid #eae7e0; border-radius: 9px;
    padding: 13px 16px; font-size: 13px; color: #4a4744; line-height: 1.75;
    max-height: 130px; overflow-y: auto; margin-bottom: 14px;
}

/* Result grid */
.res-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }
.res-card { background: #f7f6f3; border: 1px solid #eae7e0; border-radius: 10px; padding: 18px 20px; }
.res-lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #9b9790; margin-bottom: 7px;
    font-family: 'JetBrains Mono', monospace;
}
.res-val { font-size: 32px; font-weight: 700; font-family: 'JetBrains Mono', monospace; line-height: 1; }
.res-sub { font-size: 11px; color: #9b9790; margin-top: 5px; }
.edge-card { grid-column: span 2; }
.e-pos { color: #16a34a; } .e-neg { color: #dc2626; } .e-neu { color: #9b9790; }

/* Section labels */
.sec-lbl {
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em;
    color: #9b9790; margin-bottom: 6px; font-family: 'JetBrains Mono', monospace;
}
.sec-head {
    font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
    color: #9b9790; margin: 36px 0 18px; font-family: 'JetBrains Mono', monospace;
    border-top: 1px solid #eae7e0; padding-top: 28px;
}

/* Market chip */
.mkt-chip {
    background: #fff; border: 1.5px solid #eae7e0; border-radius: 9px;
    padding: 12px 16px; margin-bottom: 7px;
    display: flex; align-items: center; justify-content: space-between;
}
.mkt-title { font-size: 13px; font-weight: 500; color: #1a1a1a; }
.mkt-price { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 700; }

/* Saved badge */
.saved-badge {
    display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10px;
    font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
    background: #f0f9ff; color: #0284c7; border: 1px solid #bae6fd;
    border-radius: 5px; padding: 3px 8px; margin-bottom: 16px;
}
</style>
""")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_secret(key, default=""):
    """Read from st.secrets (Streamlit Cloud) with fallback to os.environ."""
    try:
        v = st.secrets.get(key)
        if v:
            return str(v)
    except Exception:
        pass
    return os.environ.get(key, default)


def _pc(p):  return "p-hi" if p >= 0.6 else ("p-mid" if p >= 0.35 else "p-lo")
def _ec(e):  return "e-pos" if e > 0.03 else ("e-neg" if e < -0.03 else "e-neu")
def _trunc(s, n=480): return (s[:n] + "…") if len(s) > n else s
def _vol(v): return f"{v/1e6:.1f}M" if v >= 1e6 else (f"{v/1e3:.0f}K" if v >= 1e3 else str(int(v)))


def _fmt_ts(ts):
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return ts[:10] if ts else ""


# ── Session state ──────────────────────────────────────────────────────────────

_DEFAULTS = {
    "client": None, "connect_error": "",
    "events": [], "selected_event": None,
    "markets": [], "selected_market": None,
    "memo": None, "page": "search",
    "saved_row": None, "forecast_saved": False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Auto-connect Kalshi on startup
if st.session_state.client is None:
    kid  = _get_secret("KALSHI_API_KEY")
    kpem = _get_secret("KALSHI_PRIVATE_KEY_PEM")
    kf   = _get_secret("KALSHI_PRIVATE_KEY_FILE")
    if kid and kpem:
        try:
            # Normalize PEM: TOML triple-quotes add a leading newline; env vars may use \n literals
            if "\\n" in kpem:
                kpem = kpem.replace("\\n", "\n")
            kpem = kpem.strip()
            st.session_state.client = KalshiClient(key_id=kid, private_key_pem=kpem.encode())
        except Exception as e:
            st.session_state.connect_error = str(e)
    elif kid and kf and Path(kf).exists():
        try:
            st.session_state.client = KalshiClient.from_files(kid, kf)
        except Exception as e:
            st.session_state.connect_error = str(e)

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style='padding:4px 0 24px;border-bottom:1px solid #252525;margin-bottom:24px;'>
        <div style='font-family:JetBrains Mono,monospace;font-size:20px;font-weight:600;color:#fff;'>◈ forecaster</div>
        <div style='font-size:11px;color:#444;margin-top:5px;font-family:JetBrains Mono,monospace;'>kalshi · claude</div>
    </div>""", unsafe_allow_html=True)

    if not st.session_state.client:
        err = st.session_state.connect_error
        st.markdown(f"""<div style='padding:9px 12px;background:#1f0e0e;border:1px solid #3a1a1a;
            border-radius:7px;margin-bottom:16px;'>
            <div style='font-family:JetBrains Mono,monospace;font-size:11px;color:#f87171;margin-bottom:6px;'>
                not connected</div>
            <div style='font-size:10px;color:#555;line-height:1.5;'>
                Set KALSHI_API_KEY and<br>KALSHI_PRIVATE_KEY_FILE<br>in your .env file.
                {"<br><br>" + err[:80] if err else ""}
            </div>
        </div>""", unsafe_allow_html=True)

    try:
        n = len(db.get_forecasts(limit=1000))
        st.markdown(f"""<div style='font-family:JetBrains Mono,monospace;font-size:11px;
            color:#444;padding:0 4px;'>{n} forecast{"s" if n != 1 else ""} saved</div>""",
            unsafe_allow_html=True)
    except Exception:
        pass

# ── Error gate ─────────────────────────────────────────────────────────────────

if not st.session_state.client:
    st.markdown("""<div style='max-width:480px;margin:100px auto;text-align:center;'>
        <div style='font-size:40px;margin-bottom:20px;'>◈</div>
        <div style='font-size:24px;font-weight:700;color:#1a1a1a;margin-bottom:12px;'>Not connected</div>
        <div style='font-size:14px;color:#9b9790;line-height:1.7;'>
            Add your credentials to <code>.env</code> in the project root:<br><br>
            <code style='background:#f0f0ed;padding:12px 16px;border-radius:8px;display:block;text-align:left;font-size:12px;'>
            KALSHI_API_KEY=your-key-id<br>
            KALSHI_PRIVATE_KEY_FILE=/path/to/key.txt<br>
            OPENROUTER_API_KEY=sk-or-...
            </code>
        </div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SEARCH
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.page == "search":

    st.markdown("""<div style='margin-bottom:28px;'>
        <div style='font-size:28px;font-weight:750;color:#1a1a1a;letter-spacing:-0.02em;line-height:1.2;'>
            What do you want to forecast?</div>
        <div style='font-size:14px;color:#9b9790;margin-top:8px;'>Browse live Kalshi prediction markets.</div>
    </div>""", unsafe_allow_html=True)

    sc, bc = st.columns([6, 1])
    with sc:
        query = st.text_input("q", placeholder="Trump, Fed rate, Bitcoin, oil, elections…",
                              label_visibility="collapsed")
    with bc:
        go = st.button("search →", use_container_width=True)

    if go:
        with st.spinner(""):
            try:
                pages = 10 if query else 3
                events, cursor = [], None
                for _ in range(pages):
                    batch, cursor = st.session_state.client.get_events(limit=100, cursor=cursor)
                    events += batch
                    if not cursor:
                        break
                if query:
                    q = query.lower()
                    events = [e for e in events if e.matches(q)]
                st.session_state.events = events
            except Exception as ex:
                st.error(str(ex))

    events = st.session_state.events

    if events:
        st.markdown(f"<div style='font-size:12px;color:#9b9790;margin:20px 0 16px;"
                    f"font-family:JetBrains Mono,monospace;'>{len(events)} events</div>",
                    unsafe_allow_html=True)
        cols = st.columns(3, gap="medium")
        for i, e in enumerate(events):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"""<div class='ev-card'>
                        <div class='ev-cat'>{e.category}</div>
                        <div class='ev-title'>{e.title}</div>
                        <div class='ev-sub'>{e.sub_title}</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("explore →", key=f"ev_{i}", use_container_width=True):
                        st.session_state.selected_event = e
                        st.session_state.selected_market = None
                        st.session_state.memo = None
                        st.session_state.saved_row = None
                        st.session_state.forecast_saved = False
                        with st.spinner(""):
                            try:
                                mkts, _ = st.session_state.client.get_markets(
                                    limit=50, event_ticker=e.event_ticker)
                                st.session_state.markets = mkts
                                if len(mkts) == 1:
                                    st.session_state.selected_market = mkts[0]
                            except Exception as ex:
                                st.error(str(ex))
                        st.session_state.page = "detail"
                        st.rerun()

    # ── Recent Analyses ────────────────────────────────────────────────────────
    try:
        past = db.get_forecasts(limit=12)
    except Exception:
        past = []

    if past:
        st.markdown("<div class='sec-head'>Recent Analyses</div>", unsafe_allow_html=True)
        pcols = st.columns(3, gap="medium")
        for i, row in enumerate(past):
            fp   = row["forecaster_prob"] or 0.0
            kp   = row["kalshi_price"]    or 0.0
            edge = row["edge"]            or 0.0
            ec   = _ec(edge)
            edge_str = (f"+{edge*100:.1f}pp" if edge > 0.03
                        else (f"{edge*100:.1f}pp" if edge < -0.03 else "~inline"))
            with pcols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"""<div class='fc-card'>
                        <div class='ev-cat'>{row.get("category") or ""}</div>
                        <div class='fc-q'>{_trunc(row["question"], 90)}</div>
                        <div class='fc-stats'>
                            <span class='fc-prob {_pc(fp)}'>{fp*100:.1f}%</span>
                            <span class='fc-sep'>vs</span>
                            <span class='fc-mkt'>{kp*100:.1f}¢ kalshi</span>
                            <span class='fc-edge {ec}'>{edge_str}</span>
                        </div>
                        <div class='fc-date'>{_fmt_ts(row["created_at"])}</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("view →", key=f"fc_{row['id']}", use_container_width=True):
                        st.session_state.saved_row = row
                        st.session_state.memo = None
                        st.session_state.page = "detail"
                        st.rerun()

    elif not events:
        st.markdown("""<div style='text-align:center;padding:80px 0;color:#c5c1ba;'>
            <div style='font-size:48px;margin-bottom:16px;font-weight:200;'>⊙</div>
            <div style='font-size:15px;'>Try "Trump", "Fed", "Bitcoin" or "oil"</div>
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DETAIL
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.page == "detail":

    if st.button("← back"):
        st.session_state.page = "search"
        st.session_state.saved_row = None
        st.session_state.memo = None
        st.session_state.forecast_saved = False
        st.rerun()

    st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)

    saved = st.session_state.saved_row

    # ── Resolve market + event data ────────────────────────────────────────────
    if saved:
        # Viewing a saved analysis
        ctx      = json.loads(saved["context_json"])
        ev_data  = ctx["event"]
        mkt      = KalshiMarket(**ctx["market"])
        memo     = ForecastMemo.model_validate_json(saved["memo_json"])
        ev_title    = ev_data.get("title", mkt.ticker)
        ev_sub      = ev_data.get("sub_title", "")
        ev_category = ev_data.get("category", "")
        is_saved_view = True
    else:
        ev      = st.session_state.selected_event
        mkt     = st.session_state.selected_market
        markets = st.session_state.markets
        memo    = st.session_state.memo
        ev_title    = ev.title    if ev else ""
        ev_sub      = ev.sub_title if ev else ""
        ev_category = ev.category  if ev else ""
        is_saved_view = False

        # Multi-market picker
        if len(markets) > 1 and mkt is None:
            st.markdown(f"<div style='font-size:20px;font-weight:700;color:#1a1a1a;margin-bottom:20px;'>"
                        f"{ev_title}</div>", unsafe_allow_html=True)
            for j, m in enumerate(markets):
                pc = _pc(m.mid_price)
                st.markdown(f"""<div class='mkt-chip'>
                    <div class='mkt-title'>{m.yes_sub_title or m.ticker}</div>
                    <div class='mkt-price {pc}'>{m.mid_price*100:.0f}¢</div>
                </div>""", unsafe_allow_html=True)
                if st.button("select", key=f"mkt_{j}"):
                    st.session_state.selected_market = m
                    st.session_state.memo = None
                    st.session_state.forecast_saved = False
                    st.rerun()
            st.stop()

        if mkt is None:
            st.warning("No open markets for this event.")
            st.stop()

    # ── Layout ─────────────────────────────────────────────────────────────────
    dcol, fcol = st.columns([55, 45], gap="large")

    # LEFT: market detail
    with dcol:
        pc     = _pc(mkt.mid_price)
        bid_s  = f"{mkt.yes_bid*100:.0f}¢"  if mkt.yes_bid  > 0 else "—"
        ask_s  = f"{mkt.yes_ask*100:.0f}¢"  if mkt.yes_ask  > 0 else "—"
        rules1 = _trunc(_strip_html(mkt.rules_primary))   if mkt.rules_primary   else ""
        rules2 = _trunc(_strip_html(mkt.rules_secondary)) if mkt.rules_secondary else ""

        rules_html = ""
        if rules1:
            rules_html += f"<div class='rules-lbl'>Resolution Rules</div><div class='rules-box'>{rules1}</div>"
        if rules2:
            rules_html += f"<div class='rules-lbl'>Settlement Rules</div><div class='rules-box'>{rules2}</div>"
        if not rules_html:
            rules_html = "<div style='font-size:13px;color:#9b9790;'>No rules available.</div>"

        with st.container(border=True):
            st.markdown(f"""
            <div style='padding:8px 10px 4px;'>
                <div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;
                            color:#e36438;margin-bottom:12px;font-family:JetBrains Mono,monospace;'>
                    {ev_category} · {ev_sub}
                </div>
                <div style='font-size:22px;font-weight:700;color:#1a1a1a;line-height:1.4;margin-bottom:4px;'>
                    {ev_title}
                </div>
                <div class='stat-row'>
                    <div class='stat'>
                        <span class='stat-lbl'>Yes Price</span>
                        <span class='stat-val {pc}'>{mkt.mid_price*100:.1f}¢</span>
                        <span class='stat-sub'>mid price</span>
                    </div>
                    <div class='stat'>
                        <span class='stat-lbl'>Bid / Ask</span>
                        <span class='stat-val' style='font-size:20px;color:#1a1a1a;'>{bid_s} / {ask_s}</span>
                    </div>
                    <div class='stat'>
                        <span class='stat-lbl'>Closes</span>
                        <span class='stat-val' style='font-size:20px;color:#1a1a1a;'>{mkt.close_date}</span>
                    </div>
                    <div class='stat'>
                        <span class='stat-lbl'>Volume</span>
                        <span class='stat-val' style='font-size:20px;color:#1a1a1a;'>{_vol(mkt.volume)}</span>
                    </div>
                </div>
                {rules_html}
            </div>
            """, unsafe_allow_html=True)

    # RIGHT: forecast panel
    with fcol:
        with st.container(border=True):
            st.markdown("<div style='padding:8px 10px 4px;'>", unsafe_allow_html=True)

            if is_saved_view:
                st.markdown(f"<div class='saved-badge'>Saved · {_fmt_ts(saved['created_at'])}</div>",
                            unsafe_allow_html=True)

            st.markdown("<div class='sec-lbl'>AI Forecast</div>", unsafe_allow_html=True)

            if memo is None:
                # New forecast — show run button
                st.markdown(f"""<div style='font-size:14px;color:#4a4744;line-height:1.7;margin-bottom:20px;'>
                    Run the forecaster to get an independent AI probability estimate
                    and compare it against the Kalshi market price.
                    <div style='margin-top:12px;font-size:11px;color:#9b9790;font-family:JetBrains Mono,monospace;'>
                        3 agents · claude-sonnet-4-6
                    </div>
                </div>""", unsafe_allow_html=True)

                if st.button("run forecaster →", use_container_width=True):
                    with st.spinner("Forecasting — takes 1–3 minutes…"):
                        try:
                            config = ForecasterConfig()
                            memo = ForecasterSystem(config).forecast(
                                question=mkt.question,
                                context=mkt.resolution_context or None,
                            )
                            st.session_state.memo = memo

                            # Save to DB
                            if not st.session_state.forecast_saved:
                                ev_ref = st.session_state.selected_event
                                db.save_forecast(
                                    ticker=mkt.ticker,
                                    event_title=ev_title,
                                    question=mkt.question,
                                    close_date=mkt.close_date,
                                    category=ev_category,
                                    kalshi_price=mkt.mid_price,
                                    memo=memo,
                                    context_dict={
                                        "market": dataclasses.asdict(mkt),
                                        "event": {
                                            "title": ev_title,
                                            "sub_title": ev_sub,
                                            "category": ev_category,
                                        },
                                    },
                                )
                                st.session_state.forecast_saved = True
                        except Exception as ex:
                            st.error(str(ex))
                    st.rerun()

            else:
                # Show results
                fp   = memo.final_probability
                kp   = saved["kalshi_price"] if is_saved_view else mkt.mid_price
                edge = fp - kp
                ec   = _ec(edge)
                el   = (f"+{edge*100:.1f}pp — underpriced" if edge > 0.03
                        else (f"{edge*100:.1f}pp — overpriced" if edge < -0.03
                              else "in line with market"))

                st.markdown(f"""<div class='res-grid'>
                    <div class='res-card'>
                        <div class='res-lbl'>Forecaster P(YES)</div>
                        <div class='res-val {_pc(fp)}'>{fp*100:.1f}%</div>
                        <div class='res-sub'>{memo.num_agents} agents · calibrated</div>
                    </div>
                    <div class='res-card'>
                        <div class='res-lbl'>Kalshi Price</div>
                        <div class='res-val' style='color:#1a1a1a;'>{kp*100:.1f}¢</div>
                        <div class='res-sub'>{"at forecast time" if is_saved_view else "live mid price"}</div>
                    </div>
                    <div class='res-card edge-card'>
                        <div class='res-lbl'>Edge</div>
                        <div class='res-val {ec}' style='font-size:18px;padding-top:5px;'>{el}</div>
                    </div>
                </div>""", unsafe_allow_html=True)

                with st.expander("Outside view"):
                    st.markdown(f"**Base rate:** {memo.agent_forecasts[0].outside_view_base_rate*100:.1f}%")
                    st.markdown(memo.outside_view_summary)

                with st.expander("Inside view & reasoning", expanded=True):
                    st.markdown(memo.supervisor_reconciliation.reconciliation_reasoning)

                with st.expander("Agent details"):
                    for a in memo.agent_forecasts:
                        st.markdown(f"**Agent {a.agent_id+1}** — {a.probability*100:.1f}% "
                                    f"*(confidence: {a.epistemic_confidence})*")
                        st.markdown(f"- **For:** {'; '.join(a.key_factors_for)}")
                        st.markdown(f"- **Against:** {'; '.join(a.key_factors_against)}")
                        st.divider()

                if memo.open_questions:
                    with st.expander("Open questions"):
                        for q in memo.open_questions:
                            st.markdown(f"- {q}")

                if not is_saved_view:
                    if st.button("run again", use_container_width=True):
                        st.session_state.memo = None
                        st.session_state.forecast_saved = False
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
