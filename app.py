# ============================================================
# app.py
# ------------------------------------------------------------
# Streamlit-gränssnittet. ALL beräkningslogik ligger i separata
# moduler (data, indicators, signals, backtest, ki_model,
# portfolio, metrics, charts) - den här filen bygger bara UI och
# kopplar ihop dem. Kör med: streamlit run app.py
# ============================================================

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import streamlit as st

import backtest
import charts
import config
import indicators
import ki_model
import metrics
import portfolio
import reentry
import research
import savings
import dataclasses
from datetime import date
import signals as signals_mod
from data import fetch_ki_barometer, fetch_fx_rate, fetch_price_series, fetch_riksbank_rate, fetch_vix

logger = logging.getLogger("simpletradingv3.app")

st.set_page_config(page_title="Trend Heatmap & Kvantanalys", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")


# ------------------------------------------------------------
# Hjälpfunktioner för presentation
# ------------------------------------------------------------
def fmt_pct(x: float, decimals: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{x:+.{decimals}f} %"


def fmt_ratio(x: float, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{x:.{decimals}f}"


H = config.help_text


def param_guide(*keys: str) -> None:
    """Mobilvänlig förklaring av parametrarna: vad de gör och vad man ska tänka på."""
    with st.expander("📖 Förklaring av parametrarna – vad ska jag tänka på?"):
        for k in keys:
            title, what, think = config.PARAM_HELP[k]
            st.markdown(f"**{title}**  \n{what}  \n*Tänk på:* {think}")


def info_expander(*keys: str) -> None:
    with st.expander("ℹ️ Vad betyder detta?"):
        for k in keys:
            label = k.replace("_", " ").upper()
            st.markdown(f"**{label}:** {config.EXPLANATIONS.get(k, '')}")


# ============================================================
# MODELLERNAS LOKALA INSTÄLLNINGAR
# ============================================================
def reset_model(prefix):
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]


st.title("Modeller & backtest")
with st.expander("Testperiod", expanded=True):
    st.button("Återställ testperiod", key="reset_period", on_click=reset_model, args=("period_",))
    period_mode = st.radio("Period för backtesten", ["Längsta tillgängliga historik", "Välj datum"], horizontal=True, key="period_mode", help=H("period_mode"))
    period_start = period_end = None
    if period_mode == "Välj datum":
        period_start = st.date_input("Startdatum", date(2012, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), key="period_start", help=H("period_dates"))
        period_end = st.date_input("Slutdatum", date.today(), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), key="period_end", help=H("period_dates"))
        if period_start > period_end:
            st.error("Startdatum måste vara före eller samma dag som slutdatum.")
            st.stop()
    st.caption("Datumen gäller båda modellerna. Inom KI-backtestet använder alla jämförelser exakt samma handelsdagar. Längsta historik beror på respektive modells valda tillgångar; faktisk period visas vid resultatet.")
    param_guide("period_mode", "period_dates")
st.info(
    "ℹ️ Experimentellt analys- och utbildningsverktyg – inte "
    "investeringsrådgivning. Historiska resultat garanterar inte "
    "framtida avkastning."
)

with st.expander("Om verktyget och riskerna"):
    st.markdown("""
Appen är ett experimentellt analys- och utbildningsverktyg.
Innehållet är inte personlig investeringsrådgivning eller en
rekommendation att köpa eller sälja.

Signaler och backtest bygger på historiska data och förenklade
antaganden. Data och beräkningar kan innehålla fel.
**Historiska resultat garanterar inte framtida avkastning.**

Alla investeringar innebär risk och du kan förlora hela eller
delar av ditt kapital. Du ansvarar själv för dina investeringsbeslut.
Gör en egen, välgrundad bedömning utifrån din ekonomi, dina mål
och din risktolerans. Använd inte appen som enda beslutsunderlag.
""")
st.caption("📈 Teknisk modell: flik 1–2   •   🌍 KI-modellen: flik 3–4   •   💰 Månadssparande: flik 5")
tab1, tab3, tab2, tab4, tab5 = st.tabs(["📈 Teknisk modell – Signaler", "🧪 Teknisk modell – Backtest", "🌍 KI-modellen – Konjunktur", "🏦 KI-modellen – Portföljbacktest", "💰 Månadssparande"])
with tab1:
    st.info("Den tekniska modellen använder SMA, RSI, MACD och VIX. Dessa signalparametrar används även i Teknisk modell – Backtest.")
    st.button("Återställ standard – teknisk modell", key="reset_technical", on_click=reset_model, args=("tech_",))
    st.subheader("Signalinställningar")
    with st.expander("Använd i strategin", expanded=True):
        use_rsi = st.checkbox("RSI som alternativ köpsignal", True, key="tech_use_rsi", help=H("tech_use_rsi"))
        use_vix = st.checkbox("VIX som alternativ köpsignal", True, key="tech_use_vix", help=H("tech_use_vix"))
        use_macd = st.checkbox("MACD som säljsignal", True, key="tech_use_macd", help=H("tech_use_macd"))
        use_sell_rsi = st.checkbox("Kräv högt RSI för MACD-sälj", True, key="tech_use_sell_rsi", disabled=not use_macd, help=H("tech_use_sell_rsi"))
        use_trend = st.checkbox("Kräv pris över SMA för köp", False, key="tech_use_trend", help=H("tech_use_trend"))
        st.caption("RSI ELLER VIX kan ge köp. Trendfiltret måste dessutom uppfyllas om det är valt. MACD ger sälj, med RSI-filter om valt. Sälj prioriteras vid samtidig köp- och säljsignal.")
        if not use_rsi and not use_vix:
            st.warning("Inga köpsignaler är aktiva. Strategin startar i kassa och gör inga köp.")
        if not use_macd:
            st.warning("Ingen säljsignal är aktiv. Eventuella köp behålls till testperiodens slut.")
    active_description = f"Köp: {' + '.join(x for x, enabled in [('RSI', use_rsi), ('VIX', use_vix)] if enabled) or 'inga'} (alternativa signaler) · Sälj: {'MACD' if use_macd else 'av'} · RSI-säljfilter: {'på' if use_macd and use_sell_rsi else 'av'} · Trendvillkor för köp: {'på' if use_trend else 'av'}"
    st.caption(active_description)
    ticker = st.text_input("Tillgång (Ticker, teknisk analys)", value=config.DEFAULT_TICKER, help=H("tech_ticker"), key="tech_ticker").upper().strip()
    with st.expander("Trösklar och perioder"):
        buy_rsi_threshold = st.slider("RSI köpgräns", 10, 45, config.DEFAULT_BUY_RSI_THRESHOLD, 1, help=H("tech_buy_rsi_threshold"), key="tech_buy_rsi_threshold")
        sell_macd_rsi_filter = st.slider("MACD/RSI säljfilter", 50, 80, config.DEFAULT_SELL_RSI_FILTER, 1, help=H("tech_sell_macd_rsi_filter"), key="tech_sell_macd_rsi_filter")
        cooldown_bars = st.slider("Signal-cooldown (handelsdagar)", 5, 60, config.DEFAULT_COOLDOWN_BARS, 1, help=H("tech_cooldown_bars"), key="tech_cooldown_bars")
        sma_trend_period = st.slider("SMA-period (huvudtrend)", 50, 300, config.DEFAULT_SMA_PERIOD, 10, help=H("tech_sma_trend_period"), key="tech_sma_trend_period")
        vix_panic_threshold = st.slider("VIX paniktröskel", 20.0, 60.0, config.DEFAULT_VIX_PANIC_THRESHOLD, 0.5, help=H("tech_vix_panic_threshold"), key="tech_vix_panic_threshold")
    with st.expander("Grafvisning"):
        show_sma = st.checkbox("Visa SMA och trendfärg", True, key="tech_show_sma")
        show_rsi = st.checkbox("Visa RSI", True, key="tech_show_rsi")
        show_macd = st.checkbox("Visa MACD", True, key="tech_show_macd")
        show_vix = st.checkbox("Visa VIX", True, key="tech_show_vix")
        st.caption("Dessa val ändrar bara diagrammen, aldrig handeln.")
        color_intensity_cap = st.slider("Heatmap-intensitet", 30, 300, config.DEFAULT_HEATMAP_CAP, 10, help="Styr endast färgstyrkan i trendgrafen. Ändrar inga signaler eller backtestresultat.", key="tech_color_intensity_cap")
        st.caption("Heatmap-intensitet ändrar endast grafens utseende, INTE signaler eller backtestresultat.")
    param_guide("tech_ticker", "tech_use_rsi", "tech_use_vix", "tech_use_macd", "tech_use_sell_rsi", "tech_use_trend",
                "tech_buy_rsi_threshold", "tech_sell_macd_rsi_filter", "tech_cooldown_bars", "tech_sma_trend_period",
                "tech_vix_panic_threshold", "tech_display")

with tab3:
    st.info("Detta backtest använder samma RSI-, MACD-, VIX- och SMA-inställningar som Teknisk modell – Signaler.")
    model_box = st.container(border=True)
    st.subheader("Handelsantaganden")
    execution_method_label = st.selectbox("Execution-metod (endast teknisk backtest)", config.EXECUTION_METHODS, index=0, help=H("tech_execution"), key="tech_execution_method_label")
    cost_bps = st.number_input("Courtage/transaktionskostnad (bps)", 0.0, 500.0, config.DEFAULT_COST_BPS, 1.0, help=H("tech_costs"), key="tech_cost_bps")
    slippage_bps = st.number_input("Slippage (bps)", 0.0, 500.0, config.DEFAULT_SLIPPAGE_BPS, 1.0, help=H("tech_costs"), key="tech_slippage_bps")
    initial_capital = st.number_input("Startkapital, teknisk backtest ($)", 1000.0, 10_000_000.0, config.DEFAULT_INITIAL_CAPITAL, 1000.0, help=H("tech_capital"), key="tech_initial_capital")
    execution_method = "open" if "Open" in execution_method_label else "close"
    tech_risk_free = st.number_input("Riskfri jämförelseränta (%)", 0.0, 8.0, 0.0, 0.1, help=H("tech_capital"), key="tech_tech_risk_free") / 100.0
    param_guide("tech_execution", "tech_costs", "tech_capital")
    with model_box:
        st.caption(active_description)
        st.markdown("**Modell som testas just nu**")
        st.write(f"Tillgång: {ticker} · SMA: {sma_trend_period} dagar · RSI köp: <{buy_rsi_threshold} · VIX köp: >{vix_panic_threshold:g} · MACD säljfilter RSI: >{sell_macd_rsi_filter} · Cooldown: {cooldown_bars} handelsdagar")
        st.write(f"Execution: {execution_method_label} · Courtage: {cost_bps/100:.2f} % · Slippage: {slippage_bps/100:.2f} % · Startkapital: {initial_capital:,.0f} USD · Riskfri jämförelseränta: {tech_risk_free:.1%}")

with tab2:
    st.button("Återställ standard – KI Konjunktur", key="reset_ki", on_click=reset_model, args=("ki_",))
    st.info("KI-signalerna är fristående. Kombinerat återköp (VIX, kreditspread, trend, RSI och tidsspärr) testas i KI-portföljbacktestet.")
    ki_sell_threshold = st.slider("KI säljgräns (överhettning)", 90, 140, config.DEFAULT_KI_SELL_THRESHOLD, 1, help=H("ki_sell"), key="ki_ki_sell_threshold")
    ki_buy_threshold = st.slider("KI köpgräns (lågkonjunktur)", 60, 110, config.DEFAULT_KI_BUY_THRESHOLD, 1, help=H("ki_buy"), key="ki_ki_buy_threshold")
    ki_duration_months = st.slider("Antal bekräftande månader", 1, 12, config.DEFAULT_KI_DURATION_MONTHS, 1, help=H("ki_months"), key="ki_ki_duration_months")
    ki_buyback_rule = st.selectbox("Återköpsregel", ["classic", "flat_or_up"], format_func=lambda k: config.KI_BUYBACK_RULES[k], key="ki_buyback_rule", help=H("ki_rule"))
    if ki_buyback_rule == "flat_or_up":
        st.caption(config.EXPLANATIONS["ki_flat_or_up"])
    else:
        st.caption("Klassisk KI-modell: köpgränsen används också som golv, och samma antal månader bekräftar köp och sälj.")
    with st.expander("Tekniska lager i KI-grafen (av/på)"):
        ki_show_vix = st.checkbox("Visa VIX-panik i grafen", False, key="ki_show_vix", help=H("ki_overlay_vix"))
        ki_show_rsi = st.checkbox("Visa Köp (negativ trend) i grafen", False, key="ki_show_rsi", help=H("ki_overlay_rsi"))
        lc1, lc2 = st.columns(2)
        ki_overlay_vix_level = lc1.number_input("VIX-tröskel (graf)", 15.0, 80.0, config.DEFAULT_VIX_PANIC_THRESHOLD, 0.5, key="ki_overlay_vix_level", help=H("ki_overlay_levels"))
        ki_overlay_rsi_level = lc2.number_input("RSI-gräns (graf)", 5.0, 50.0, float(config.DEFAULT_BUY_RSI_THRESHOLD), 1.0, key="ki_overlay_rsi_level", help=H("ki_overlay_levels"))
        st.caption("Lagren visar bara var signalerna hade kommit. Vill du se om de förbättrar resultatet, välj Kombinerat återköp i Portföljbacktestet.")
    st.caption("Inställningarna här är separata från portföljbacktestet.")
    param_guide("ki_sell", "ki_buy", "ki_months", "ki_rule", "ki_overlay_vix", "ki_overlay_rsi", "ki_overlay_levels")

with tab4:
    st.button("Återställ standard – KI Portföljbacktest", key="reset_pf", on_click=reset_model, args=("pf_",))
    pf_model_box = st.container(border=True)
    st.caption("Inställningarna här påverkar endast KI-portföljbacktestet, inklusive jämförelserna nedan.")
    with st.expander("KI-signal"):
        pf_ki_sell_threshold = st.slider("KI säljgräns (överhettning)", 90, 140, config.DEFAULT_KI_SELL_THRESHOLD, 1, help=H("ki_sell"), key="pf_pf_ki_sell_threshold")
        pf_ki_buy_threshold = st.slider("KI köpgräns (lågkonjunktur)", 60, 110, config.DEFAULT_KI_BUY_THRESHOLD, 1, help=H("ki_buy"), key="pf_pf_ki_buy_threshold")
        pf_ki_duration_months = st.slider("Antal bekräftande månader", 1, 12, config.DEFAULT_KI_DURATION_MONTHS, 1, help=H("ki_months"), key="pf_pf_ki_duration_months")
        pf_ki_buyback_rule = st.selectbox("Återköpsregel", list(config.KI_BUYBACK_RULES.keys()), index=0, format_func=lambda k: config.KI_BUYBACK_RULES[k], help=H("ki_rule"), key="pf_pf_ki_buyback_rule")
        pf_ki_floor_threshold = st.slider("Golv som måste passeras före återköp", 60, 110, config.DEFAULT_KI_FLOOR_THRESHOLD, 1, help=H("ki_floor"), key="pf_pf_ki_floor_threshold", disabled=pf_ki_buyback_rule == "flat_or_up")
        pf_ki_effective_floor = pf_ki_buy_threshold if pf_ki_buyback_rule == "flat_or_up" else pf_ki_floor_threshold
        if pf_ki_buyback_rule == "flat_or_up":
            st.caption(config.EXPLANATIONS["ki_flat_or_up"] + " Det separata golvet används inte för denna regel.")
        pf_pub_lag = st.slider("Publiceringsfördröjning (dagar efter månadsslut)", 0, 30, config.KI_PUBLICATION_LAG_DAYS, 1, key="pf_pub_lag", help=H("ki_lag"))
    with st.expander("Återköp – kombinerade signaler (valfritt)", expanded=False):
        reentry_mode = st.radio("Återköpsläge", list(config.REENTRY_MODES.keys()), format_func=lambda k: config.REENTRY_MODES[k],
                                key="pf_reentry_mode", help=H("reentry_mode"))
        combined = reentry_mode == "combined"
        re_ki = st.checkbox("Steg: KI-vändning (vald återköpsregel)", True, key="pf_re_ki", disabled=not combined, help=H("re_ki"))
        re_vix = st.checkbox("Steg: VIX-panik", True, key="pf_re_vix", disabled=not combined, help=H("re_vix"))
        rv1, rv2 = st.columns(2)
        re_vix_threshold = rv1.number_input("VIX-tröskel för panik", 15.0, 80.0, config.DEFAULT_REENTRY_VIX_THRESHOLD, 0.5, key="pf_re_vix_threshold", disabled=not (combined and re_vix), help=H("re_vix_threshold"))
        re_vix_calm = rv2.number_input("Köp när VIX åter är under (0 = direkt)", 0.0, 60.0, config.DEFAULT_REENTRY_VIX_CALM, 0.5, key="pf_re_vix_calm", disabled=not (combined and re_vix), help=H("re_vix_calm"))
        re_credit = st.checkbox("Steg: Kreditspread vänder (HYG/IEF)", False, key="pf_re_credit", disabled=not combined, help=H("re_credit"))
        rc1, rc2 = st.columns(2)
        re_credit_stress = rc1.number_input("Kreditstress: fall från 1-årstopp (%)", 1.0, 30.0, config.DEFAULT_REENTRY_CREDIT_STRESS, 0.5, key="pf_re_credit_stress", disabled=not (combined and re_credit), help=H("re_credit_stress"))
        re_credit_sma = rc2.number_input("Kreditspread: medelvärde (dagar)", 10, 200, config.DEFAULT_REENTRY_CREDIT_SMA, 5, key="pf_re_credit_sma", disabled=not (combined and re_credit), help=H("re_credit_sma"))
        re_rsi = st.checkbox("Steg: Köp (negativ trend) – RSI under SMA 200", False, key="pf_re_rsi", disabled=not combined, help=H("re_rsi"))
        re_rsi_threshold = st.number_input("RSI-gräns", 5.0, 50.0, config.DEFAULT_REENTRY_RSI, 1.0, key="pf_re_rsi_threshold", disabled=not (combined and re_rsi), help=H("re_rsi_threshold"))
        re_trend = st.checkbox("Steg: Trendvändning", True, key="pf_re_trend", disabled=not combined, help=H("re_trend"))
        re_trend_mode = st.selectbox("Trendmått", list(reentry.TREND_MODES.keys()), format_func=lambda k: reentry.TREND_MODES[k], key="pf_re_trend_mode", disabled=not (combined and re_trend), help=H("re_trend_mode"))
        re_time_stop = st.number_input("Tidsspärr: köp tillbaka resten efter (månader, 0 = av)", 0, 60, config.DEFAULT_REENTRY_TIME_STOP, 1, key="pf_re_time_stop", disabled=not combined, help=H("re_time_stop"))
        re_staged = st.checkbox("Köp i lika stora steg (trappa)", True, key="pf_re_staged", disabled=not combined, help=H("re_staged"))
        reentry_params = reentry.ReentryParams(
            use_ki=re_ki, use_vix=re_vix, vix_threshold=float(re_vix_threshold), vix_calm_level=float(re_vix_calm),
            use_credit=re_credit, credit_stress_pct=float(re_credit_stress), credit_sma=int(re_credit_sma),
            use_rsi=re_rsi, rsi_threshold=float(re_rsi_threshold), use_trend=re_trend, trend_mode=re_trend_mode,
            time_stop_months=int(re_time_stop), staged=re_staged)
        if combined:
            n_steps = len(reentry_params.triggers())
            if n_steps == 0 and reentry_params.time_stop_months == 0:
                st.warning("Inga återköpsvillkor är valda. Efter en försäljning köper modellen aldrig tillbaka.")
            elif n_steps == 0:
                st.caption(f"Endast tidsspärren köper tillbaka, {reentry_params.time_stop_months} månader efter försäljningen.")
            else:
                share = f"{100 / n_steps:.0f} % av det sålda per steg" if re_staged else "allt på första uppfyllda villkor"
                st.caption(f"{n_steps} återköpssteg: {share}. Dagliga villkor använder föregående handelsdags stängning. Trend och RSI räknas på portföljens egna aktier (viktat index i SEK).")
        else:
            st.caption("Välj 'Kombinerat återköp i steg' för att aktivera inställningarna ovan.")
    with st.expander("Trendfilter för KI (valfritt)"):
        pf_trend = st.checkbox("Använd trendfilter för KI-återköp", False, key="pf_trend", disabled=combined, help=H("pf_trend"))
        if combined:
            pf_trend = False
            st.caption("Ersätts av steget 'Trendvändning' i kombinerat återköp.")
        st.caption("Trendfilter: efter KI-köpbesked väntar återköpet tills portföljens egna aktier (viktat index i SEK, föregående handelsdag) är över SMA 200. En ny KI-säljsignal avbryter väntande köp.")
    with st.expander("Portfölj"):
        w_global = st.slider("Vikt Global (%)", 0, 100, int(config.DEFAULT_PORTFOLIO_WEIGHTS["global"] * 100), 1, help=H("pf_weights"), key="pf_w_global")
        w_sweden = st.slider("Vikt Sverige (%)", 0, 100, int(config.DEFAULT_PORTFOLIO_WEIGHTS["sweden"] * 100), 1, help=H("pf_weights"), key="pf_w_sweden")
        w_em = st.slider("Vikt Emerging Markets (%)", 0, 100, int(config.DEFAULT_PORTFOLIO_WEIGHTS["em"] * 100), 1, help=H("pf_weights"), key="pf_w_em")
        rebalance_freq = st.selectbox("Rebalansering", list(config.REBALANCE_OPTIONS.keys()), index=list(config.REBALANCE_OPTIONS.keys()).index(config.DEFAULT_REBALANCE), format_func=lambda k: config.REBALANCE_OPTIONS[k], help=H("pf_rebalance"), key="pf_rebalance_freq")
        portfolio_initial_capital = st.number_input("Startkapital, KI-portfölj (kr)", 1000.0, 100_000_000.0, 100_000.0, 1000.0, help=H("pf_capital"), key="pf_portfolio_initial_capital")
        pf_cost_bps = st.number_input("Courtage/transaktionskostnad (bps)", 0.0, 500.0, config.DEFAULT_COST_BPS, 1.0, help=H("pf_costs"), key="pf_cost_bps")
        pf_slippage_bps = st.number_input("Slippage (bps)", 0.0, 500.0, config.DEFAULT_SLIPPAGE_BPS, 1.0, help=H("pf_costs"), key="pf_slippage_bps")
    with st.expander("Avriskning"):
        ki_scope = st.selectbox("KI-signalen påverkar", list(config.KI_SIGNAL_SCOPE_OPTIONS.keys()), index=0, format_func=lambda k: config.KI_SIGNAL_SCOPE_OPTIONS[k], help=H("pf_scope"), key="pf_ki_scope")
        derisk_pct = st.select_slider("Minska aktieexponeringen med", options=config.DERISK_LEVELS, value=config.DEFAULT_DERISK_LEVEL, help=H("pf_derisk"), key="pf_derisk_pct")
    with st.expander("Defensiv placering"):
        interest_mode = st.selectbox("Räntekonto", list(config.INTEREST_MODES.keys()), index=list(config.INTEREST_MODES.keys()).index(config.DEFAULT_INTEREST_MODE), format_func=lambda k: config.INTEREST_MODES[k], help=H("pf_interest"), key="pf_interest_mode")
        hist_rate = interest_mode == "historical"
        annual_interest_rate = st.slider("Fast årlig ränta (%) – används i läget Fast ränta och som reserv", 0.0, 8.0, config.DEFAULT_ANNUAL_INTEREST_RATE * 100, 0.1, help=H("pf_interest"), key="pf_annual_interest_rate", disabled=interest_mode == "zero") / 100.0
        ic1, ic2 = st.columns(2)
        interest_deduction = ic1.number_input("Avdrag från räntan (%/år)", 0.0, 3.0, config.DEFAULT_INTEREST_DEDUCTION, 0.05, key="pf_interest_deduction", disabled=not hist_rate, help=H("pf_interest_deduction"))
        interest_floor_zero = ic2.checkbox("Aldrig under 0 % (som sparkonto)", config.DEFAULT_INTEREST_FLOOR_ZERO, key="pf_interest_floor", disabled=not hist_rate, help=H("pf_interest_floor"))
        if hist_rate:
            st.caption(f"Källa: {config.RIKSBANK_RATE_LABEL}, Riksbankens öppna API (gratis, ingen nyckel). Räntan som gällde föregående handelsdag används varje dag.")
        else:
            st.caption("Fast ränta eller nollränta under hela perioden.")
    param_guide("ki_sell", "ki_buy", "ki_months", "ki_rule", "ki_floor", "ki_lag", "reentry_mode", "re_ki", "re_vix",
                "re_vix_threshold", "re_vix_calm", "re_credit", "re_credit_stress", "re_credit_sma", "re_rsi",
                "re_rsi_threshold", "re_trend", "re_trend_mode", "re_time_stop", "re_staged", "pf_trend", "pf_weights",
                "pf_rebalance", "pf_capital", "pf_costs", "pf_scope", "pf_derisk", "pf_interest", "pf_interest_deduction",
                "pf_interest_floor", "pf_robust", "pf_sweden_long")
    weight_sum = w_global + w_sweden + w_em
    base_weights = {k: v for k, v in {"global": w_global/100, "sweden": w_sweden/100, "em": w_em/100}.items() if v > 0}
    risk_free_annual = annual_interest_rate if interest_mode == "fixed" else 0.0
    if interest_mode == "historical":
        interest_desc = f"historisk statsskuldväxel 3 mån" + (f" − {interest_deduction:.2f} %" if interest_deduction else "") + (", golv 0 %" if interest_floor_zero else "")
    else:
        interest_desc = f"{risk_free_annual:.1%}"
    with pf_model_box:
        if combined:
            steps_txt = ", ".join(reentry.TRIGGER_LABELS[t] for t in reentry_params.triggers()) or "inga"
            st.caption(f"KI styr sälj · Kombinerat återköp: {steps_txt}" + (f" · Tidsspärr {reentry_params.time_stop_months} mån" if reentry_params.time_stop_months else "") + (" · trappa" if re_staged else " · allt på första signalen"))
        else:
            st.caption(f"KI styr köp och sälj · Trendfilter för återköp: {'portföljens SMA 200' if pf_trend else 'av'} · RSI, MACD och VIX påverkar inte KI.")
        st.markdown("**Modell som testas just nu**")
        st.write(f"KI sälj: >{pf_ki_sell_threshold} i {pf_ki_duration_months} månader · Köpgräns: <{pf_ki_buy_threshold} · Aktiveringsnivå/golv: <{pf_ki_effective_floor} · Återköp: {config.KI_BUYBACK_RULES[pf_ki_buyback_rule]}")
        st.write(f"Avriskning: {derisk_pct} % av {config.KI_SIGNAL_SCOPE_OPTIONS[ki_scope]} · Defensiv ränta: {interest_desc} · Portfölj: {w_global}/{w_sweden}/{w_em} · Rebalansering: {config.REBALANCE_OPTIONS[rebalance_freq]}")
        st.write(f"Startkapital: {portfolio_initial_capital:,.0f} kr · Courtage: {pf_cost_bps/100:.2f} % · Slippage: {pf_slippage_bps/100:.2f} % · Handel: Close efter publiceringsfördröjning ({pf_pub_lag} dagar)")

scope_key_map = {"all": {"global", "sweden", "em"}, "sweden_only": {"sweden"}, "sweden_em": {"sweden", "em"}}
# ============================================================
# DATAHÄMTNING (FLIK 1-3: teknisk analys)
# ============================================================


raw_price = fetch_price_series(ticker)
raw_vix = fetch_vix()

technical_available = raw_price is not None and not raw_price.empty
if not technical_available:
    with tab1:
        st.error(f"Kunde inte hämta marknadsdata för {ticker}. Kontrollera börssymbolen.")
    with tab3:
        st.info("Tekniskt backtest behöver prisdata. KI-flikarna kan fortfarande användas.")
else:
    df = raw_price.copy()
    if raw_vix is not None:
        df = df.join(raw_vix, how="left")
        df["VIX"] = df["VIX"].ffill()
    else:
        df["VIX"] = np.nan
        st.warning("⚠️ VIX-data kunde inte hämtas just nu. VIX-panik-signalen kommer inte att kunna triggas.")

    df = indicators.calculate_technical_indicators(df, sma_trend_period, config.DEFAULT_RSI_PERIOD)

    sig_params = signals_mod.SignalParams(
        buy_rsi_threshold=buy_rsi_threshold,
        sell_rsi_filter=sell_macd_rsi_filter,
        vix_panic_threshold=vix_panic_threshold,
        cooldown_bars=cooldown_bars,
        use_rsi_buy=use_rsi, use_vix_buy=use_vix,
        use_macd_sell=use_macd, use_rsi_sell_filter=use_sell_rsi,
        use_trend_filter=use_trend,
    )
    # Warm up indicators on full history; cooldown and orders start inside the selected window.
    df = research.select_period(df, period_start, period_end)
    if len(df) < 2:
        with tab3:
            st.warning("Otillräcklig teknisk prishistorik under vald period.")
        technical_available = False
    df = signals_mod.generate_signals(df, sig_params)

    if technical_available:
        latest = df.iloc[-1]
        latest_price = float(latest["Close"])
        latest_vix = float(latest["VIX"]) if not np.isnan(latest["VIX"]) else None
        latest_rsi = float(latest["RSI"]) if not np.isnan(latest["RSI"]) else None
        latest_sma = float(latest["SMA"]) if not np.isnan(latest["SMA"]) else None
        trend_is_positive = (latest_sma is not None) and (latest_price > latest_sma)

        signal_rows = df[df["Signal"] != 0]
        last_signal_row = signal_rows.iloc[-1] if not signal_rows.empty else None


        def _collect_markers(sub: pd.DataFrame) -> dict:
            out = {"buy_neg": ([], []), "buy_pos": ([], []), "sell": ([], []), "vix_buy_neg": ([], []), "vix_buy_pos": ([], [])}
            for date, row in sub.iterrows():
                sma = row["SMA"]
                pos_trend = (not np.isnan(sma)) and row["Close"] > sma
                if row["Signal"] == 1 and row["Signal_Type"] == "VIX Panik KÖP":
                    key = "vix_buy_pos" if pos_trend else "vix_buy_neg"
                elif row["Signal"] == 1:
                    key = "buy_pos" if pos_trend else "buy_neg"
                elif row["Signal"] == -1:
                    key = "sell"
                else:
                    continue
                d, p = out[key]
                d.append(date)
                p.append(row["Close"])
            return out


        markers = _collect_markers(signal_rows)

        # ------------------------------------------------------------
        # FLIK 1: TEKNISK TRENDANALYS
        # ------------------------------------------------------------
        with tab1:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                trend_label = "📗 POSITIV" if trend_is_positive else "📕 NEGATIV"
                days_in_trend = int(abs(df["Streak"].iloc[-1]))
                st.metric("Nuvarande trend", trend_label, delta=f"{days_in_trend} dagar i trend", help=config.EXPLANATIONS["trend"])
            with c2:
                st.metric("RSI (14)", f"{latest_rsi:.1f}" if latest_rsi is not None else "N/A (warm-up)", delta=f"Köp < {buy_rsi_threshold}", delta_color="off", help=config.EXPLANATIONS["rsi"])
            with c3:
                if last_signal_row is not None:
                    date_str = pd.Timestamp(last_signal_row.name).strftime("%Y-%m-%d")
                    emoji = "🟢" if "KÖP" in str(last_signal_row["Signal_Type"]) else "🔴"
                    st.metric("Senaste signal", f"{emoji} {last_signal_row['Signal_Type']}", delta=date_str, delta_color="off")
                else:
                    st.metric("Senaste signal", "Ingen signal")
            with c4:
                st.metric(f"Pris ({ticker})", f"${latest_price:.2f}")

            info_expander("sma", "rsi", "macd", "trend", "cooldown")
            st.markdown("---")

            st.subheader("🌡️ VIX-panikmätare")
            if latest_vix is not None:
                vc1, vc2 = st.columns([2, 3])
                with vc1:
                    vix_status = "Över paniktröskeln" if latest_vix > vix_panic_threshold else "✅ Normalt marknadsläge"
                    st.metric("VIX just nu", f"{latest_vix:.2f}", delta=f"{latest_vix - vix_panic_threshold:+.2f} vs tröskel", delta_color="inverse", help=config.EXPLANATIONS["vix"])
                    st.markdown(f"**Status:** {vix_status}")
                with vc2:
                    vix_pct = min(latest_vix / (vix_panic_threshold * 1.5), 1.0)
                    bar_color = "🟥" if latest_vix > vix_panic_threshold else ("🟨" if latest_vix > vix_panic_threshold * 0.75 else "🟩")
                    filled = int(vix_pct * 20)
                    st.markdown(f"**VIX-nivå:** `{bar_color * filled}{'⬜' * (20 - filled)}`")
            else:
                st.info("VIX-data är inte tillgänglig för tillfället.")

            st.markdown("---")
            fig = charts.build_trend_heatmap_chart(df, ticker, sma_trend_period, color_intensity_cap, markers)
            if not show_sma:
                for trace in fig.data:
                    if trace.name.startswith('SMA') or trace.name in ('Positiv Trend', 'Negativ Trend'):
                        trace.visible = False
            for label, cols, visible in [('RSI', ['RSI'], show_rsi), ('MACD', ['MACD', 'MACD_Signal'], show_macd), ('VIX', ['VIX'], show_vix)]:
                if visible:
                    with st.expander(f"Diagram: {label}"):
                        st.line_chart(df[cols])
            st.plotly_chart(fig, width="stretch")
            st.caption("Data via Yahoo Finance · Auto-adjusted för utdelningar/split · Cache: 1 timme")

# ------------------------------------------------------------
# FLIK 2: MAKRO & KONJUNKTURMODELL
# ------------------------------------------------------------
with tab2:
    st.subheader("📊 Konjunkturbarometermodell (Konjunkturinstitutet)")
    st.markdown(
        "Konjunkturmodellen använder KI:s Barometerindikator för att identifiera extrema delar av "
        "konjunkturcykeln. Idén är **konträr**: vid mycket stark konjunktur/överhettning minskas "
        "aktieexponeringen, vid mycket svag konjunktur ökas den igen. Detta är en **långsiktig** modell "
        "och skiljer sig fundamentalt från de kortsiktiga RSI/MACD/VIX-signalerna i den tekniska modellen. "
        "Modellen är historisk och **garanterar inte** framtida resultat. Läs mer om ursprungsidén: "
        "https://cornucopia.se/2015/02/konjunkturmodellen-haller-fortfarande/"
    )
    info_expander("ki_barometer", "ki_sell", "ki_buy", "ki_months")

    df_ki = fetch_ki_barometer()
    if df_ki is None or df_ki.empty:
        st.warning("⚠️ Kunde inte hämta data från Konjunkturinstitutets API just nu. Detta kan bero på ett tillfälligt driftstopp hos statistik.konj.se. Försök ladda om sidan senare.")
    else:
        secondary_df = fetch_price_series(config.SWEDEN_ORIGINAL_TICKER)

        ki_params_sidebar = ki_model.KiParams(
            sell_threshold=ki_sell_threshold,
            buy_threshold=ki_buy_threshold,
            duration_months=ki_duration_months,
            floor_threshold=ki_buy_threshold,
            buyback_rule=ki_buyback_rule,
        )
        ki_signals_monthly = ki_model.generate_ki_signals(df_ki["Barometer"], ki_params_sidebar)

        ki_daily = ki_signals_monthly.reindex(pd.date_range(ki_signals_monthly.index.min(), df_ki.index.max(), freq="D"))
        ki_daily["Barometer"] = ki_daily["Barometer"].ffill()
        if secondary_df is not None and not secondary_df.empty:
            df_combo = secondary_df[["Close"]].join(ki_daily["Barometer"], how="left").ffill().dropna()
        else:
            df_combo = pd.DataFrame({"Close": 100., "Barometer": ki_daily["Barometer"]}, index=ki_daily.index)
            st.caption("Sverigepris saknas; prisjämförelsen visas som en konstant referens.")

        k1, k2, k3 = st.columns(3)
        with k1:
            latest_ki = float(df_ki["Barometer"].iloc[-1])
            status = "🔴 ÖVERHETTNING" if latest_ki > ki_sell_threshold else ("🟢 LÅGKONJUNKTUR" if latest_ki < ki_buy_threshold else "⚪ NEUTRAL")
            st.metric("Barometerindikator", f"{latest_ki:.1f}", delta=status, delta_color="off")
        with k2:
            st.metric("Senaste KI-månad", pd.Timestamp(df_ki.index[-1]).strftime("%Y-%m"))
        with k3:
            sig_hist = ki_signals_monthly[ki_signals_monthly["Signal"] != 0]
            if not sig_hist.empty:
                last = sig_hist.iloc[-1]
                emoji = "🟢" if last["Signal"] == 1 else "🔴"
                st.metric("Senaste KI-signal", f"{emoji} {last['Signal_Type']}", delta=pd.Timestamp(sig_hist.index[-1]).strftime("%Y-%m"), delta_color="off")
            else:
                st.metric("Senaste KI-signal", "Ingen signal")

        # --- Nuläge: allt som styr beslutet samlat på ett ställe ---
        se_close = secondary_df["Close"].dropna() if secondary_df is not None and not secondary_df.empty else None
        with st.container(border=True):
            st.markdown("**🧭 Nuläge – vad säger signalerna idag?**")
            n1, n2, n3, n4 = st.columns(4)
            vals = df_ki["Barometer"].dropna()
            months_over = 0
            for v in vals.iloc[::-1]:
                if v > ki_sell_threshold:
                    months_over += 1
                else:
                    break
            n1.metric("Månader i följd över säljgränsen", f"{months_over} av {ki_duration_months}",
                      help="Hur många av de senaste KI-månaderna som legat över din säljgräns. Säljsignal när antalet når antalet bekräftande månader.")
            state_now = str(ki_signals_monthly["State"].iloc[-1])
            state_txt, state_detail = {"NORMAL": ("Investerad", "väntar på överhettning"),
                                       "DERISKED": ("Sålt", f"väntar på KI < {ki_buy_threshold:g}"),
                                       "FLOOR_REACHED": ("Sålt", "väntar på återköpsregeln")}.get(state_now, (state_now, ""))
            n2.metric("KI-modellens läge", state_txt, delta=state_detail, delta_color="off", help="Enligt inställningarna i denna flik och hela KI-historiken.")
            if raw_vix is not None and not raw_vix.dropna().empty:
                vix_now = float(raw_vix.dropna().iloc[-1])
                n3.metric("VIX", f"{vix_now:.1f}", delta=f"{vix_now - ki_overlay_vix_level:+.1f} mot tröskel", delta_color="inverse",
                          help="Senaste stängning. Över tröskeln = panik enligt grafens VIX-lager.")
            else:
                n3.metric("VIX", "saknas")
            if se_close is not None and len(se_close) >= 200:
                sma_now = float(se_close.rolling(200).mean().iloc[-1])
                trend_pos = float(se_close.iloc[-1]) > sma_now
                n4.metric(f"Trend Sverige ({config.SWEDEN_ORIGINAL_TICKER})", "📗 Positiv" if trend_pos else "📕 Negativ",
                          delta=f"{(float(se_close.iloc[-1]) / sma_now - 1) * 100:+.1f} % mot SMA 200", delta_color="off",
                          help="Sverigepriset (USD) mot sitt 200-dagars medelvärde.")
            else:
                n4.metric(f"Trend Sverige ({config.SWEDEN_ORIGINAL_TICKER})", "saknas")
            st.caption("Nuläget är en sammanställning, inte en rekommendation. Portföljbacktestets egna inställningar kan skilja sig från denna flik.")

        st.markdown("---")
        buy_dates = ki_signals_monthly[ki_signals_monthly["Signal"] == 1].index
        sell_dates = ki_signals_monthly[ki_signals_monthly["Signal"] == -1].index
        df_combo = research.select_period(df_combo, period_start, period_end)
        if not df_combo.empty:
            buy_dates = buy_dates[(buy_dates >= df_combo.index.min()) & (buy_dates <= df_combo.index.max())]
            sell_dates = sell_dates[(sell_dates >= df_combo.index.min()) & (sell_dates <= df_combo.index.max())]
        overlays = {}
        if ki_show_vix:
            if raw_vix is not None and not raw_vix.dropna().empty:
                overlays["vix"] = (f"VIX-panik (> {ki_overlay_vix_level:g})", list(research.episode_starts(raw_vix.dropna() > ki_overlay_vix_level)))
            else:
                st.caption("VIX-data saknas just nu; VIX-lagret kan inte visas.")
        if ki_show_rsi:
            if se_close is not None and len(se_close) > 200:
                se_rsi = indicators.compute_rsi(se_close, config.DEFAULT_RSI_PERIOD)
                se_sma = se_close.rolling(200, min_periods=200).mean()
                overlays["rsi"] = (f"Köp (negativ trend): RSI < {ki_overlay_rsi_level:g} under SMA 200",
                                   list(research.episode_starts((se_rsi < ki_overlay_rsi_level) & (se_close < se_sma))))
            else:
                st.caption("Sverigepris saknas; RSI-lagret kan inte visas.")
        fig_ki = charts.build_ki_chart(df_combo, config.SWEDEN_ORIGINAL_TICKER, ki_sell_threshold, ki_buy_threshold, buy_dates, sell_dates, overlays)
        st.plotly_chart(fig_ki, width="stretch")
        st.caption(
            f"KI-data datumstämplas vid månadsslut och antas tillgänglig först {config.KI_PUBLICATION_LAG_DAYS} "
            "dagar senare (schablon). Historiska värden kan vara reviderade; testet återskapar inte säkert dåtidens information. Markörerna här visar signalmånader, inte handelsdagar."
        )

# ------------------------------------------------------------
# FLIK 3: TEKNISK BACKTEST
# ------------------------------------------------------------
if technical_available:
    with tab3:
        st.subheader("📊 Kvantitativ backtest: Signalmodell vs. Buy & Hold")
        st.markdown(
            "Signaler exekveras **tidigast nästa handelsdag** efter att de uppstått (ingen retroaktiv handel). "
            f"Execution-metod: **{execution_method_label}**. Courtage: **{cost_bps:.0f} bps**, slippage: **{slippage_bps:.0f} bps**."
        )

        exec_params = backtest.ExecutionParams(
            initial_capital=initial_capital, cost_bps=cost_bps, slippage_bps=slippage_bps, execution_method=execution_method, require_sma=False
        )
        bt = backtest.run_technical_backtest(df, exec_params)

        if bt is None:
            st.warning("Otillräcklig historisk data för att genomföra backtestet med vald SMA-period.")
        else:
            st.caption(f"Faktisk teknisk testperiod: {bt['equity'].index.min().date()} till {bt['equity'].index.max().date()} · USD")
            st.caption(f"Längsta tid under tidigare topp: {research.longest_underwater_days(bt['equity'])} kalenderdagar · Avslutade affärer: {sum(t['status'] == 'closed' for t in bt['trades'])}")
            strat_report = metrics.build_risk_report(bt["equity"], bt["position"], bt["trades"], risk_free_annual=tech_risk_free)
            bnh_position = pd.Series(1, index=bt["bnh_equity"].index)
            bnh_report = metrics.build_risk_report(bt["bnh_equity"], bnh_position, [], risk_free_annual=tech_risk_free)

            st.markdown("#### Avkastning")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Totalavkastning (Strategi)", fmt_pct(strat_report.total_return_pct), delta=f"{strat_report.total_return_pct - bnh_report.total_return_pct:+.1f} procentenheter mot köp och behåll", help=config.EXPLANATIONS["total_return"])
            m1.caption(f"Slutvärde: **${strat_report.final_value:,.0f}**")
            m2.metric("Totalavkastning (Buy & Hold)", fmt_pct(bnh_report.total_return_pct), delta="Referens", delta_color="off")
            m2.caption(f"Slutvärde: **${bnh_report.final_value:,.0f}**")
            m3.metric("CAGR (Strategi)", fmt_ratio(strat_report.cagr_pct) + " %/år", delta=fmt_pct(strat_report.cagr_pct - bnh_report.cagr_pct, 2), help=config.EXPLANATIONS["cagr"])
            m4.metric("CAGR (Buy & Hold)", fmt_ratio(bnh_report.cagr_pct) + " %/år", delta="Referens", delta_color="off")

            st.markdown("#### Risk")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Max Drawdown (Strategi)", fmt_pct(strat_report.max_drawdown_pct), help=config.EXPLANATIONS["mdd"])
            r2.metric("Max Drawdown (Buy & Hold)", fmt_pct(bnh_report.max_drawdown_pct))
            r3.metric("Sharpe Ratio", fmt_ratio(strat_report.sharpe), help=config.EXPLANATIONS["sharpe"])
            r4.metric("Sortino Ratio", fmt_ratio(strat_report.sortino), help=config.EXPLANATIONS["sortino"])

            st.markdown("#### Affärer & exponering")
            ts = strat_report.trade_stats
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Avslutade affärer", ts.n_closed)
            a2.metric("Öppna affärer", ts.n_open)
            a3.metric("Win Rate", fmt_ratio(ts.win_rate_pct, 1) + " %" if ts.win_rate_pct is not None else "N/A", help=config.EXPLANATIONS["win_rate"])
            a4.metric("Profit Factor", metrics.format_profit_factor(ts.profit_factor), help=config.EXPLANATIONS["profit_factor"])
            st.caption(f"Marknadsexponering: **{strat_report.exposure_pct:.1f} %** · Calmar Ratio: **{fmt_ratio(strat_report.calmar)}**")

            info_expander("cagr", "total_return", "mdd", "sharpe", "sortino", "calmar", "win_rate", "profit_factor", "exposure", "slippage", "cost")

            st.markdown("---")
            strat_dd = metrics.compute_drawdown(bt["equity"].to_numpy())
            bnh_dd = metrics.compute_drawdown(bt["bnh_equity"].to_numpy())
            fig_bt = charts.build_equity_drawdown_chart(bt["equity"], bt["bnh_equity"], strat_dd, bnh_dd, "Aktiv Signalmodell")
            charts.add_transactions(fig_bt, bt["equity"], charts.technical_events(bt["trades"]), bt["position"])
            st.caption("Grön bakgrund: investerad. Grå: kassa. Markörer och streckade linjer visar genomförda affärer. Hovra för signal- och executionsdatum.")
            st.plotly_chart(fig_bt, width="stretch")

            if bt["trades"]:
                with st.expander("📋 Detaljerad affärslogg (avslutade och ev. öppen affär visas separat)"):
                    st.dataframe(charts.trade_log(bt["trades"]), width="stretch", hide_index=True)
                    st.caption("Avkastning visar kursförändring; Resultat i USD inkluderar courtage. Öppna affärer visar orealiserad avkastning och saknar säljdatum.")

# ------------------------------------------------------------
# FLIK 4: KI-PORTFÖLJBACKTEST
# ------------------------------------------------------------
savings_ctx = None  # fylls i när portföljdata finns; används av fliken Månadssparande
with tab4:
    st.subheader("🏦 KI-portföljbacktest: Konjunkturmodellen som allokeringsstrategi")
    st.markdown(
        "Detta är en **helt separat backtestmotor** från den tekniska modellen ovan. Den testar hur "
        "Konjunkturmodellen fungerar som strategi för att allokera om en bred, global portfölj - "
        "**inte** som en signal för en enskild aktie."
    )
    info_expander("currency", "rebalance", "ki_scope", "derisk_pct", "risk_free")

    if weight_sum != 100:
        st.error("Portföljvikterna ovan summerar inte till 100 %. Justera dem för att köra backtesten.")
    else:
        proxy_symbols = {k: v["ticker"] for k, v in config.PORTFOLIO_PROXIES.items() if k in base_weights}
        st.caption("Proxys som används: " + " · ".join(f"**{k}** = {v['label']}" for k, v in config.PORTFOLIO_PROXIES.items() if k in base_weights))

        raw_prices = {k: fetch_price_series(sym) for k, sym in proxy_symbols.items()}
        fx = fetch_fx_rate()

        missing = [k for k, v in raw_prices.items() if v is None or v.empty]
        if missing:
            st.error(f"❌ Kunde inte hämta data för: {', '.join(missing)}. KI-portföljbacktesten kan inte köras just nu.")
        elif fx is None or fx.empty:
            st.error("❌ Kunde inte hämta USD/SEK-växelkurs. KI-portföljbacktesten kan inte köras just nu.")
        elif df_ki is None or df_ki.empty:
            st.error("❌ KI-barometerdata saknas (se KI-modellen – Konjunktur). KI-portföljbacktesten kan inte köras just nu.")
        else:
            prices_sek = {k: portfolio.to_common_currency(v["Close"], fx) for k, v in raw_prices.items()}
            full_prices = portfolio.align_prices(prices_sek)
            prices_df = research.select_period(full_prices, period_start, period_end)
            if len(prices_df) < 2:
                st.error("Otillräcklig gemensam historik efter valutakonvertering; minst två datum krävs.")
                st.stop()
            st.warning("KI-resultatet kan bygga på få konjunkturcykler. Perioden begränsas endast av tillgångar med positiv vikt samt valutadata. Se faktisk period nedan.")
            with st.expander("Data och antaganden"):
                st.write(f"KI: senast hämtade historiska serie, som kan vara reviderad. Antagen tillgänglighet: månadsslut + {pf_pub_lag} kalenderdagar (KI publicerar normalt i slutet av samma månad); handel tidigast följande handelsdag. Detta är inte verifierade historiska publiceringsdatum och undanröjer inte effekten av reviderade värden.")
                st.markdown("[KI: data uppdateras vid publicering](https://www.konj.se/statistik-och-data/) · [KI: indikatorer revideras varje månad](https://www.konj.se/publikationer/konjunkturbarometern/2026-09-29-kraftigt-forbattrat-stamningslage-hos-hushallen/)")
                st.caption("Startallokering följer senast kända KI-/trendbeslut före perioden. Saknas tidigare beslut startar KI-portföljen fullt investerad. Teknisk strategi startar i kassa. Kassa i KI får vald schablonränta; historisk kortränta används inte.")
            st.caption(f"Faktisk backteststart och slut: {prices_df.index.min().date()} till {prices_df.index.max().date()} · Basvaluta: {config.DEFAULT_BASE_CURRENCY}")

            st.caption(f"Kostnad per omsatt aktievärde: courtage {pf_cost_bps:g} + slippage {pf_slippage_bps:g} bps, även initialköp och Buy & Hold-rebalansering. Riskfri ränta: {risk_free_annual:.1%}.")

            ki_params_sidebar = ki_model.KiParams(
                sell_threshold=pf_ki_sell_threshold, buy_threshold=pf_ki_buy_threshold,
                duration_months=pf_ki_duration_months, floor_threshold=pf_ki_floor_threshold, buyback_rule=pf_ki_buyback_rule,
                publication_lag_days=pf_pub_lag,
            )
            ki_signals_monthly = ki_model.generate_ki_signals(df_ki["Barometer"], ki_params_sidebar)
            sweden_raw = raw_prices.get('sweden')
            if sweden_raw is None:
                sweden_raw = fetch_price_series(config.SWEDEN_ORIGINAL_TICKER)
            sweden_reference = None if sweden_raw is None or sweden_raw.empty else portfolio.to_common_currency(sweden_raw['Close'], fx).dropna()
            # Trend- och RSI-villkor räknas på portföljens egna aktier (viktat index i SEK av
            # tillgångarna med vikt), så att t.ex. 100 % Global följer Globals trend.
            # Sverige-fördjupningarna nedan använder fortsatt Sverigepriset.
            trend_reference = portfolio.weighted_index(full_prices, base_weights)

            # --- Räntekonto: historisk ränta från Riksbanken, fast ränta eller 0 % ---
            interest_rates = None
            effective_interest_mode = interest_mode
            if interest_mode == "historical":
                interest_rates = portfolio.effective_rate_series(fetch_riksbank_rate(), interest_deduction, interest_floor_zero)
                if interest_rates is None:
                    st.warning(f"⚠️ Historisk ränta kunde inte hämtas från Riksbanken just nu. Fast ränta {annual_interest_rate:.1%} används i stället. Försök ladda om sidan senare.")
                    effective_interest_mode = "fixed"
                else:
                    risk_free_annual = portfolio.average_rate(interest_rates, prices_df.index.min(), prices_df.index.max(), annual_interest_rate)
                    st.caption(f"Räntekonto: {config.RIKSBANK_RATE_LABEL}"
                               + (f" − {interest_deduction:.2f} %" if interest_deduction else "")
                               + (", aldrig under 0 %" if interest_floor_zero else "")
                               + f". Snitt under perioden: **{risk_free_annual:.2%} per år** (används även i Sharpe/Sortino). "
                               + f"Senaste observation: {interest_rates.index.max().date()}.")
            if effective_interest_mode == "fixed":
                risk_free_annual = annual_interest_rate

            # --- Kombinerat återköp: villkoren beräknas en gång och återanvänds i alla jämförelser ---
            credit_ratio = None
            if combined and re_credit:
                hyg = fetch_price_series(config.CREDIT_TICKERS[0])
                ief = fetch_price_series(config.CREDIT_TICKERS[1])
                if hyg is None or ief is None or hyg.empty or ief.empty:
                    st.warning("Kreditdata (HYG/IEF) kunde inte hämtas just nu. Kreditsteget kan inte utlösas; övriga steg fungerar.")
                else:
                    credit_ratio = (hyg["Close"] / ief["Close"]).dropna()
            # Motorns dagkalender: portföljens handelsdagar plus Sveriges (längre) historik, så att
            # VIX-/kreditvillkor och tidsspärr kan följas även före portföljens första kursdag.
            # Trendvillkoret är okänt tills portföljens egen trend har värmts upp.
            engine_calendar = full_prices.index if sweden_reference is None else full_prices.index.union(sweden_reference.index)
            reentry_conditions = reentry.prepare_conditions(engine_calendar, reentry_params, reference=trend_reference,
                                                            vix=raw_vix, credit_ratio=credit_ratio) if combined else None
            _sweden_conditions_cache = {}

            def sweden_conditions():
                """Samma villkor men med Sverigepriset som trendreferens (för Sverige-fördjupningen)."""
                if "c" not in _sweden_conditions_cache:
                    _sweden_conditions_cache["c"] = reentry.prepare_conditions(engine_calendar, reentry_params, reference=sweden_reference,
                                                                               vix=raw_vix, credit_ratio=credit_ratio)
                return _sweden_conditions_cache["c"]

            def combined_run(kp, conditions=None):
                return reentry.run_reentry_engine(df_ki["Barometer"], kp, engine_calendar,
                                                  reentry_conditions if conditions is None else conditions, reentry_params)

            def execution_for(monthly, use_filter=None, kp=None, calendar=None, period_index=None, ki_only=False,
                              reference=None, conditions=None):
                """Ordrar för vald modell, mappade till kalendern och avgränsade till perioden.

                reference/conditions: trendreferens (standard: portföljens eget index)."""
                calendar = full_prices.index if calendar is None else calendar
                period_index = prices_df.index if period_index is None else period_index
                reference = trend_reference if reference is None else reference
                if combined and not ki_only:
                    orders = reentry.map_orders_to_calendar(combined_run(kp or ki_params_sidebar, conditions)["orders"], calendar)
                else:
                    orders = ki_model.map_signals_to_trading_days(monthly, calendar)
                    if (pf_trend if use_filter is None else use_filter):
                        orders = research.trend_orders(orders, reference, calendar)
                return research.orders_for_period(orders, period_index)

            ki_exec_signals = execution_for(ki_signals_monthly)
            main_run = combined_run(ki_params_sidebar) if combined else None
            if main_run is not None:
                stt = main_run["state"]
                if stt["out"]:
                    waiting = ", ".join(reentry.TRIGGER_LABELS[t] for t in stt["pending"]) or "–"
                    ts_txt = f" · Tidsspärr: {pd.Timestamp(stt['time_stop_date']).date()}" if stt["time_stop_date"] is not None else ""
                    st.info(f"**Läge idag:** sålt, {stt['exposure']:.0%} av det sålda återköpt. Väntar på: {waiting}{ts_txt}.")
                else:
                    st.info(f"**Läge idag:** investerad. KI över säljgränsen {stt['months_over']} av {pf_ki_duration_months} månader"
                            + ("" if stt["armed"] else " (ny försäljning kräver att KI först går ned till säljgränsen)") + ".")

            pf_params = portfolio.PortfolioParams(
                base_weights=base_weights, rebalance_freq=rebalance_freq, scope_keys=scope_key_map[ki_scope],
                derisk_pct=float(derisk_pct), interest_mode=effective_interest_mode, annual_interest_rate=annual_interest_rate,
                interest_rates=interest_rates, cost_bps=pf_cost_bps, slippage_bps=pf_slippage_bps,
                initial_capital=portfolio_initial_capital, apply_ki=True,
            )
            savings_ctx = {"full_prices": full_prices, "pf_params": pf_params, "execution_for": execution_for,
                           "ki_signals_monthly": ki_signals_monthly, "interest_desc": interest_desc,
                           "risk_free_annual": risk_free_annual}
            result = portfolio.run_ki_vs_bnh(prices_df, ki_exec_signals, pf_params)
            ki_res, bnh_res = result["ki"], result["bnh"]

            ki_pos = pd.Series((1.0 - ki_res["weights"]["cash"]).to_numpy(), index=ki_res["equity"].index)
            bnh_pos = pd.Series((1.0 - bnh_res["weights"]["cash"]).to_numpy(), index=bnh_res["equity"].index)
            ki_report = metrics.build_risk_report(ki_res["equity"], (ki_pos > 0).astype(int), [], risk_free_annual=risk_free_annual)
            bnh_report = metrics.build_risk_report(bnh_res["equity"], (bnh_pos > 0).astype(int), [], risk_free_annual=risk_free_annual)
            ki_exposure = float(ki_pos.mean() * 100.0)
            bnh_exposure = float(bnh_pos.mean() * 100.0)

            st.markdown(f"#### Huvudjämförelse: {w_global}% Global / {w_sweden}% Sverige / {w_em}% Emerging Markets")
            value1, value2 = st.columns(2)
            value1.metric("Slutvärde KI-strategi", f"{ki_report.final_value:,.0f} kr")
            value2.metric("Slutvärde köp och behåll", f"{bnh_report.final_value:,.0f} kr")
            st.caption(f"Avslutade sälj–återköpscykler: {research.completed_cycles(ki_res['events'])} · Längsta tid under tidigare topp: KI {research.longest_underwater_days(ki_res['equity'])} dagar / köp och behåll {research.longest_underwater_days(bnh_res['equity'])} dagar (kalenderdagar, även pågående nedgång). Startallokering räknas inte som en affärscykel.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Totalavkastning (KI-strategi)", fmt_pct(ki_report.total_return_pct), delta=f"{ki_report.total_return_pct - bnh_report.total_return_pct:+.1f} procentenheter mot köp och behåll")
            m1.caption(f"Slutvärde: **{ki_report.final_value:,.0f} kr**")
            m2.metric("Totalavkastning (Buy & Hold)", fmt_pct(bnh_report.total_return_pct), delta="Referens", delta_color="off")
            m2.caption(f"Slutvärde: **{bnh_report.final_value:,.0f} kr**")
            m3.metric("CAGR (KI-strategi)", fmt_ratio(ki_report.cagr_pct) + " %/år")
            m4.metric("CAGR (Buy & Hold)", fmt_ratio(bnh_report.cagr_pct) + " %/år")

            r1, r2 = st.columns(2)
            r1.metric("Max Drawdown (KI)", fmt_pct(ki_report.max_drawdown_pct))
            r2.metric("Max Drawdown (B&H)", fmt_pct(bnh_report.max_drawdown_pct))
            with st.expander("Fördjupning – riskjusterade mått"):
                r3, r4 = st.columns(2)
                r3.metric("Sharpe (KI) / (B&H)", f"{fmt_ratio(ki_report.sharpe)} / {fmt_ratio(bnh_report.sharpe)}")
                r4.metric("Calmar (KI) / (B&H)", f"{fmt_ratio(ki_report.calmar)} / {fmt_ratio(bnh_report.calmar)}")
            st.caption(f"Tid i aktier — KI: **{ki_exposure:.1f} %**, B&H: **{bnh_exposure:.1f} %** · Tid defensivt/räntekonto — KI: **{100 - ki_exposure:.1f} %**, B&H: **{100 - bnh_exposure:.1f} %**")

            st.markdown("---")
            strat_dd = metrics.compute_drawdown(ki_res["equity"].to_numpy(), portfolio_initial_capital)
            bnh_dd = metrics.compute_drawdown(bnh_res["equity"].to_numpy(), portfolio_initial_capital)
            fig_pf = charts.build_equity_drawdown_chart(ki_res["equity"], bnh_res["equity"], strat_dd, bnh_dd, "KI-portfölj")
            marker_text = st.toggle("Visa text vid markörerna (stäng av i mobilen om det blir trångt)", True, key="pf_marker_text")
            charts.add_transactions(fig_pf, ki_res["equity"], charts.portfolio_events(ki_res["events"]), ki_res["risk_multiplier"], marker_text)
            if main_run is not None and reentry_params.time_stop_months > 0:
                charts.add_time_stop_lines(fig_pf, [c["time_stop_date"] for c in main_run["cycles"]],
                                           ki_res["equity"].index[0], ki_res["equity"].index[-1])
            st.plotly_chart(fig_pf, width="stretch")
            st.caption("Grön bakgrund: fullt investerad. Gul: delvis återköpt (trappa). Grå: avriskat läge. Markörerna visar faktiska omallokeringar och vilken signal som utlöste dem; hovra för datum, aktieandelar och belopp. Lila prickad linje: där tidsspärren skulle slå till. Avriskningsprocenten gäller vald portföljdel.")
            st.plotly_chart(charts.build_exposure_chart(1.0 - ki_res["weights"]["cash"]), width="stretch")
            st.caption("Aktieandel i KI-portföljen. I trappan kliver andelen upp i steg.")

            with st.expander("Affärslogg – varför köpte eller sålde modellen?"):
                if ki_res['events']:
                    st.dataframe(research.ki_trade_log(ki_res['events']), width="stretch", hide_index=True)
                else:
                    st.caption("Inga omallokeringar efter startdagen under perioden.")
                st.caption(f"Startläge: {ki_res['weights']['cash'].iloc[0]:.1%} räntekonto. Signalmånad och antaget publiceringsdatum visas separat från handelsdagen.")

            fig_ind = charts.build_ki_indicator_chart(research.select_period(ki_signals_monthly, prices_df.index.min(), prices_df.index.max()), pf_ki_sell_threshold, pf_ki_buy_threshold, pf_ki_effective_floor)
            st.plotly_chart(fig_ind, width="stretch")
            if combined:
                st.caption("Grafen ovan visar KI:s egna månadssignaler enligt vald KI-regel. I kombinerat återköp kan återköpet ha skett tidigare (se markörerna i kapitalgrafen), och en ny försäljning kräver då att KI först varit nere på säljgränsen.")

            with st.expander("Fördjupning – portföljsammansättning"):
                label_map = {k: config.PORTFOLIO_PROXIES[k]["label"].split(" (")[0] for k in base_weights} | {"cash": "Räntekonto"}
                fig_alloc = charts.build_allocation_chart(ki_res["weights"], label_map)
                st.plotly_chart(fig_alloc, width="stretch")

            with st.expander("Fördjupning – resultat per portföljdel"):
                rows = []
                for key in list(base_weights.keys()) + ["cash"]:
                    ki_series = ki_res["components"][key]
                    bnh_series = bnh_res["components"][key]
                    rows.append(
                        {
                            "Del": label_map.get(key, key),
                            "Buy & Hold totalavk.": fmt_pct(metrics.total_return(bnh_series)),
                            "KI-styrd totalavk.": fmt_pct(metrics.total_return(ki_series)),
                        }
                    )
                rows.append(
                    {"Del": "Total portfölj", "Buy & Hold totalavk.": fmt_pct(bnh_report.total_return_pct), "KI-styrd totalavk.": fmt_pct(ki_report.total_return_pct)}
                )
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                st.caption(
                    "OBS: Eftersom kapital flyttas mellan delarna vid rebalansering/KI-signaler är dessa "
                    "kurvor inte renodlade 'köp och behåll enbart den tillgången'-kurvor, utan visar respektive "
                    "sleeves faktiska bidrag inom den simulerade portföljen."
                )

            with st.expander("Fördjupning – avriskningsgrad × återköpsregel"):
                st.caption("Historisk jämförelse - optimera INTE parametrarna mot denna tabell och förvänta dig samma resultat framåt.")
                sweep_rows = []
                for rule_key, rule_label in config.KI_BUYBACK_RULES.items():
                    rule_params = ki_model.KiParams(pf_ki_sell_threshold, pf_ki_buy_threshold, pf_ki_duration_months, pf_ki_floor_threshold, rule_key, publication_lag_days=pf_pub_lag)
                    sig_monthly_rule = ki_model.generate_ki_signals(df_ki["Barometer"], rule_params)
                    exec_rule = execution_for(sig_monthly_rule, kp=rule_params)
                    for lvl in config.DERISK_LEVELS:
                        if lvl == 0:
                            continue
                        p = dataclasses.replace(pf_params, derisk_pct=float(lvl))
                        res = portfolio.simulate_portfolio(prices_df, exec_rule, p)
                        sweep_rows.append(
                            {
                                "Avriskning": f"{lvl} %",
                                "Återköpsregel": rule_label,
                                "CAGR": fmt_ratio(metrics.cagr(res["equity"])) + " %",
                                "Max DD": fmt_ratio(metrics.max_drawdown(res["equity"])) + " %",
                                "Sharpe": fmt_ratio(metrics.sharpe_ratio(res["equity"], risk_free_annual=risk_free_annual)),
                                "Sortino": fmt_ratio(metrics.sortino_ratio(res["equity"], risk_free_annual=risk_free_annual)),
                                "Calmar": fmt_ratio(metrics.calmar_ratio(res["equity"])),
                                "Slutvärde": f"{res['equity'].iloc[-1]:,.0f} kr",
                            }
                        )
                sweep_df = pd.DataFrame(sweep_rows)
                st.dataframe(sweep_df, width="stretch", hide_index=True)
                st.caption("Tabellen markerar avsiktligt INTE en enskild 'bästa' rad - jämför gärna både CAGR och de riskjusterade måtten (Sharpe/Sortino/Calmar).")

            with st.expander("Fördjupning – återköpsvarianter (enbart KI, trendfilter, kombinerat)"):
                st.caption("Samma period, kostnader och KI-säljregel. Endast återköpet ändras. Trendfiltret väntar på att portföljens egna aktier (föregående dag, SEK) är över SMA 200. Kombinerat återköp använder dina val ovan.")
                variants = []
                candidates = [("Enbart KI", execution_for(ki_signals_monthly, False, ki_only=True)),
                              ("KI + trendfilter", execution_for(ki_signals_monthly, True, ki_only=True))]
                if combined:
                    candidates.append(("Kombinerat återköp", ki_exec_signals))
                candidates.append(("Köp och behåll", None))
                for name, orders in candidates:
                    variant = portfolio.simulate_portfolio(prices_df, orders, pf_params if orders is not None else dataclasses.replace(pf_params, apply_ki=False))
                    variants.append({"Strategi": name,
                                     "Slutvärde (kr)": round(variant['equity'].iloc[-1]),
                                     "Årsavkastning (%)": round(metrics.cagr(variant['equity']), 2),
                                     "Största nedgång (%)": round(metrics.max_drawdown(variant['equity']), 1),
                                     "Avslutade cykler": research.completed_cycles(variant['events']) if orders is not None else 0})
                st.dataframe(pd.DataFrame(variants), width="stretch", hide_index=True)

            with st.expander("Fördjupning – hur nära toppen sålde modellen?"):
                st.caption("Varje försäljning mäts mot köp och behåll-portföljen. Topp = högsta värdet från ett år före försäljningen till fullt återköp. "
                           "Negativa 'Dagar från topp' = sålde före toppen. 'Återköpsnivå mot sälj' under 0 = köpte tillbaka billigare än du sålde.")
                ev_table = research.sell_event_table(ki_res["events"], bnh_res["equity"])
                if ev_table.empty:
                    st.caption("Inga försäljningar under perioden.")
                else:
                    st.dataframe(ev_table.round(1), width="stretch", hide_index=True)

            with st.expander("Fördjupning – robusthetstest: säljgräns × bekräftande månader"):
                st.caption("Kör hela backtestet för säljgräns 105–118 och 1–4 bekräftande månader med dina övriga inställningar. "
                           "Ett robust val ligger i ett område med liknande färg – inte som en ensam grön ruta.")
                if st.checkbox("Kör robusthetstestet (tar några sekunder)", False, key="pf_robust_run", help=H("pf_robust")):
                    bnh_cagr = metrics.cagr(bnh_res["equity"])
                    bnh_mdd = metrics.max_drawdown(bnh_res["equity"])
                    grid_rows = []
                    progress = st.progress(0.0)
                    grid = [(t, m) for m in range(1, 5) for t in range(105, 119)]
                    for n_done, (t, m) in enumerate(grid, start=1):
                        kp = dataclasses.replace(ki_params_sidebar, sell_threshold=float(t), duration_months=m)
                        monthly = None if combined else ki_model.generate_ki_signals(df_ki["Barometer"], kp)
                        res = portfolio.simulate_portfolio(prices_df, execution_for(monthly, kp=kp), pf_params)
                        grid_rows.append({"Säljgräns": t, "Månader": m,
                                          "CAGR mot köp och behåll (pe)": metrics.cagr(res["equity"]) - bnh_cagr,
                                          "Mindre största nedgång (pe)": metrics.max_drawdown(res["equity"]) - bnh_mdd,
                                          "Avslutade cykler": research.completed_cycles(res["events"])})
                        progress.progress(n_done / len(grid))
                    progress.empty()
                    grid_df = pd.DataFrame(grid_rows)
                    current = (int(pf_ki_sell_threshold), int(pf_ki_duration_months))
                    st.plotly_chart(charts.build_robustness_heatmap(grid_df, "CAGR mot köp och behåll (pe)", "Årsavkastning mot köp och behåll (pe)", current), width="stretch")
                    st.plotly_chart(charts.build_robustness_heatmap(grid_df, "Mindre största nedgång (pe)", "Mindre största nedgång (pe)", current), width="stretch")
                    st.caption("pe = procentenheter jämfört med köp och behåll. Svart ram = dina nuvarande inställningar (om de ligger inom rutnätet). Positiva tal är bättre än köp och behåll. "
                               "Få konjunkturcykler betyder att en enda försäljning kan avgöra en hel ruta.")

            with st.expander("Fördjupning – Sverige med längsta historik"):
                st.caption("Samma KI-modell och återköp, men enbart Sverige (EWD i SEK) så långt tillbaka som kurs- och valutadata räcker. "
                           "Ger fler konjunkturcykler än huvudtestet, som begränsas av Global-proxyns start.")
                if st.checkbox("Kör Sverige med längsta historik", False, key="pf_sweden_long", help=H("pf_sweden_long")):
                    if sweden_reference is None or sweden_reference.empty:
                        st.info("Sverigedata saknas.")
                    else:
                        long_prices = research.select_period(sweden_reference.to_frame("sweden"), period_start, period_end)
                        if len(long_prices) < 2:
                            st.info("För lite Sverigedata under vald period.")
                        else:
                            long_orders = execution_for(ki_signals_monthly, calendar=sweden_reference.index, period_index=long_prices.index,
                                                        reference=sweden_reference, conditions=sweden_conditions() if combined else None)
                            long_params = dataclasses.replace(pf_params, base_weights={"sweden": 1.0}, scope_keys={"sweden"})
                            long_ki = portfolio.simulate_portfolio(long_prices, long_orders, long_params)
                            long_bnh = portfolio.simulate_portfolio(long_prices, None, dataclasses.replace(long_params, apply_ki=False))
                            st.caption(f"Period: {long_prices.index.min().date()} till {long_prices.index.max().date()} · Avslutade cykler: {research.completed_cycles(long_ki['events'])}")
                            l1, l2, l3, l4 = st.columns(4)
                            l1.metric("CAGR KI Sverige (lång)", fmt_ratio(metrics.cagr(long_ki['equity'])) + " %/år")
                            l2.metric("CAGR köp och behåll (lång)", fmt_ratio(metrics.cagr(long_bnh['equity'])) + " %/år")
                            l3.metric("Största nedgång KI (lång)", fmt_ratio(metrics.max_drawdown(long_ki['equity'])) + " %")
                            l4.metric("Största nedgång köp och behåll (lång)", fmt_ratio(metrics.max_drawdown(long_bnh['equity'])) + " %")
                            lfig = charts.build_equity_drawdown_chart(long_ki["equity"], long_bnh["equity"],
                                                                      metrics.compute_drawdown(long_ki["equity"].to_numpy(), portfolio_initial_capital),
                                                                      metrics.compute_drawdown(long_bnh["equity"].to_numpy(), portfolio_initial_capital), "KI Sverige")
                            charts.add_transactions(lfig, long_ki["equity"], charts.portfolio_events(long_ki["events"]), long_ki["risk_multiplier"], marker_text)
                            if main_run is not None and reentry_params.time_stop_months > 0:
                                charts.add_time_stop_lines(lfig, [c["time_stop_date"] for c in main_run["cycles"]],
                                                           long_ki["equity"].index[0], long_ki["equity"].index[-1])
                            st.plotly_chart(lfig, width="stretch")
                            sell_tbl = research.sell_event_table(long_ki["events"], long_bnh["equity"])
                            if not sell_tbl.empty:
                                st.dataframe(sell_tbl.round(1), width="stretch", hide_index=True)

            st.markdown("---")
            if w_sweden != 100:
                with st.expander("Fördjupning – Sverige under samma period"):
                    st.caption("Samma handelsdagar, affärsdatum och kostnader som huvudjämförelsen (affärerna styrs av huvudportföljens signaler). Här tillämpas avriskningen på Sverige.")
                    sweden_only_prices = None
                    if sweden_reference is not None:
                        sweden_only_prices = sweden_reference.reindex(sweden_reference.index.union(prices_df.index)).sort_index().ffill().reindex(prices_df.index).to_frame('sweden')
                    if sweden_only_prices is None or sweden_only_prices.isna().any().any():
                        st.info("Sverigedata täcker inte hela den valda perioden. Ingen jämförelse med annan period visas.")
                    else:
                        st.caption(f"Sverigejämförelsens faktiska period: {prices_df.index.min().date()} till {prices_df.index.max().date()}.")
                        sweden_params = dataclasses.replace(pf_params, base_weights={'sweden': 1.0}, scope_keys={'sweden'})
                        sweden_result = portfolio.run_ki_vs_bnh(sweden_only_prices, ki_exec_signals, sweden_params)
                        s1, s2, s3, s4 = st.columns(4)
                        s1.metric("CAGR KI-strategi Sverige", fmt_ratio(metrics.cagr(sweden_result['ki']['equity'])) + " %/år")
                        s2.metric("CAGR Sverige Buy & Hold", fmt_ratio(metrics.cagr(sweden_result['bnh']['equity'])) + " %/år")
                        s3.metric("Max DD KI-strategi", fmt_ratio(metrics.max_drawdown(sweden_result['ki']['equity'])) + " %")
                        s4.metric("Max DD Buy & Hold", fmt_ratio(metrics.max_drawdown(sweden_result['bnh']['equity'])) + " %")

# ------------------------------------------------------------
# FLIK 5: MÅNADSSPARANDE
# ------------------------------------------------------------
def fmt_kr(x: float) -> str:
    return "N/A" if x is None or not np.isfinite(x) else f"{x:,.0f} kr".replace(",", " ")


def fmt_pp(x: float, decimals: int = 2) -> str:
    return "N/A" if x is None or not np.isfinite(x) else f"{x:.{decimals}f} %"


with tab5:
    st.subheader("💰 Månadssparande – vad hade hänt med din sparplan?")
    st.markdown(
        "Testa ett månadssparande med årlig höjning, ett startbelopp och valfritt antal större insättningar (bonus, arv, försäljning …). "
        "Samma insättningar körs i **köp och behåll** och i **KI-strategin**. Portfölj, KI-regler, avriskning, "
        "räntekonto och kostnader hämtas från fliken **KI-modellen – Portföljbacktest**. "
        "Testperioden överst gäller inte här – välj start och slut för sparandet nedan."
    )
    st.button("Återställ standard – Månadssparande", key="reset_sv", on_click=reset_model, args=("sv_",))
    with st.expander("Sparplan", expanded=True):
        c1, c2 = st.columns(2)
        sv_start = c1.date_input("Började spara", date(2007, 1, 1), min_value=date(1990, 1, 1), max_value=date(2100, 12, 31), key="sv_start", help=H("sv_period"))
        sv_end = c2.date_input("Slutdatum", date.today(), min_value=date(1990, 1, 1), max_value=date(2100, 12, 31), key="sv_end", help=H("sv_period"))
        c3, c4 = st.columns(2)
        sv_initial = c3.number_input("Startbelopp (kr)", 0.0, 100_000_000.0, 0.0, 1000.0, format="%.0f", key="sv_initial", help=H("sv_initial"))
        sv_monthly = c4.number_input("Månadsbelopp (kr)", 0.0, 1_000_000.0, 2000.0, 100.0, format="%.0f", key="sv_monthly", help=H("sv_monthly"))
        c5, c6 = st.columns(2)
        sv_growth = c5.number_input("Årlig ökning av månadsbeloppet (%)", 0.0, 20.0, 3.0, 0.5, format="%.1f", key="sv_growth", help=H("sv_growth"))
        sv_day = int(c6.number_input("Insättningsdag i månaden", 1, 28, 25, 1, key="sv_day", help=H("sv_day")))
    with st.expander("Extra insättningar (bonus, arv, försäljning …)", expanded=True):
        st.caption("Lägg till så många insättningar du vill: klicka på den tomma raden längst ner i tabellen "
                   "(eller **+** i tabellens verktygsrad uppe till höger). Dubbelklicka på en cell för att ändra den. "
                   "Ta bort en rad genom att markera rutan längst till vänster och klicka på papperskorgen.")
        # Startdata ligger i en egen nyckel; redigeringarna lagras av tabellen själv (sv_extra_table).
        if "sv_extra_data" not in st.session_state:
            st.session_state["sv_extra_data"] = savings.empty_extra_table()
        extra_table = st.data_editor(
            st.session_state["sv_extra_data"], num_rows="dynamic", key="sv_extra_table", width="stretch", hide_index=True,
            column_config={
                "Datum": st.column_config.DateColumn("Datum", format="YYYY-MM-DD", min_value=date(1990, 1, 1), max_value=date(2100, 12, 31)),
                "Belopp (kr)": st.column_config.NumberColumn("Belopp (kr)", min_value=0, step=1000, format="%.0f"),
                "Beskrivning": st.column_config.TextColumn("Beskrivning (valfritt)", max_chars=60),
            })
        sv_extra_rows, sv_extra_incomplete = savings.parse_extra_deposits(extra_table)
        sv_extras = [(n, d, a) for n, d, a, _ in sv_extra_rows]
        sv_extra_label = {n: lbl for n, _, _, lbl in sv_extra_rows}
        if sv_extra_incomplete:
            st.warning(f"{sv_extra_incomplete} rad(er) saknar datum eller belopp över 0 kr och räknas inte.")
        if sv_extra_rows:
            extra_total = f"{sum(a for _, _, a, _ in sv_extra_rows):,.0f}".replace(",", " ")
            st.caption(f"{len(sv_extra_rows)} extra insättningar, totalt {extra_total} kr.")
        st.caption("Tips: lägg en insättning strax före en topp (t.ex. hösten 2007 eller december 2021) och en strax efter ett ras för att se skillnaden.")
    param_guide("sv_period", "sv_initial", "sv_monthly", "sv_day", "sv_growth", "sv_extra", "sv_compare")

    if savings_ctx is None:
        st.info("Portföljdata saknas. Kontrollera fliken KI-modellen – Portföljbacktest: vikterna måste summera till 100 % och kurs-, valuta- och KI-data måste kunna hämtas.")
    elif sv_start > sv_end:
        st.error("Startdatum måste vara före slutdatum.")
    else:
        fp = savings_ctx["full_prices"]
        data_start, data_end = fp.index.min(), fp.index.max()
        start_ts = max(pd.Timestamp(sv_start), data_start)
        end_ts = min(pd.Timestamp(sv_end), data_end)
        if pd.Timestamp(sv_start) < data_start:
            hint = (" Global (URTH) finns från 2012. Vill du testa från t.ex. 2007, sätt 100 % Sverige i Portföljbacktestet."
                    if "global" in base_weights else "")
            st.info(f"Kursdata för vald portfölj börjar {data_start.date()}, så sparandet startar då.{hint}")
        sv_prices = fp.loc[start_ts:end_ts]
        if len(sv_prices) < 2:
            st.error("För kort sparperiod med tillgänglig kursdata.")
        else:
            plan = savings.SavingsPlan(start=start_ts, end=end_ts, initial_amount=float(sv_initial), monthly_amount=float(sv_monthly),
                                       deposit_day=sv_day, annual_increase_pct=float(sv_growth),
                                       extra=[(d, a) for _, d, a in sv_extras])
            flows = savings.map_to_trading_days(savings.build_contributions(plan), sv_prices.index)
            outside = [n for n, d, _ in sv_extras if not (start_ts <= d <= sv_prices.index[-1])]
            if outside:
                names = [f"rad {n}" + (f" ({sv_extra_label[n]})" if sv_extra_label.get(n) else "") for n in outside]
                st.warning("Extra insättning " + ", ".join(names) + " ligger utanför sparperioden och räknas inte.")
            if flows.sum() <= 0:
                st.info("Ange ett startbelopp, ett månadsbelopp eller en extra insättning.")
            else:
                sv_params = savings_ctx["pf_params"]
                sv_orders = savings_ctx["execution_for"](savings_ctx["ki_signals_monthly"], period_index=sv_prices.index)
                plan_res = savings.run_plan(sv_prices, sv_orders, sv_params, flows)
                ki_s, bnh_s = plan_res["ki_summary"], plan_res["bnh_summary"]
                st.caption(f"Sparperiod: {sv_prices.index.min().date()} till {sv_prices.index.max().date()} · "
                           f"Portfölj: {w_global}/{w_sweden}/{w_em} (Global/Sverige/EM) · Räntekonto: {savings_ctx['interest_desc']} · "
                           f"{len(flows)} insättningar")

                a1, a2, a3 = st.columns(3)
                a1.metric("Insatt totalt", fmt_kr(bnh_s["invested"]))
                a2.metric("Slutvärde köp och behåll", fmt_kr(bnh_s["final_value"]), delta=f"{bnh_s['profit']:+,.0f} kr vinst".replace(",", " "))
                a3.metric("Slutvärde KI-strategi", fmt_kr(ki_s["final_value"]),
                          delta=f"{ki_s['final_value'] - bnh_s['final_value']:+,.0f} kr mot köp och behåll".replace(",", " "))
                st.markdown("**Årsavkastning på dina insättningar** (pengaviktad, tar hänsyn till när pengarna sattes in)")
                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Köp och behåll", fmt_pp(bnh_s["xirr_pct"]),
                          help="Pengaviktad avkastning (XIRR): den årliga avkastning dina insättningar fick, med hänsyn till när de gjordes.")
                b2.metric("KI-strategi", fmt_pp(ki_s["xirr_pct"]),
                          help="Pengaviktad avkastning (XIRR) för KI-strategin med samma insättningar.",
                          delta=f"{ki_s['xirr_pct'] - bnh_s['xirr_pct']:+.2f} pe" if np.isfinite(ki_s['xirr_pct']) and np.isfinite(bnh_s['xirr_pct']) else None)
                b3.metric("Tidsviktad, KI / köp och behåll", f"{fmt_pp(ki_s['twr_cagr_pct'])} / {fmt_pp(bnh_s['twr_cagr_pct'])}",
                          help="Strategins egen avkastning per år oberoende av när pengarna sattes in. Jämförbar med CAGR i Portföljbacktestet.")
                b4.metric("Största nedgång, KI / köp och behåll", f"{fmt_pp(ki_s['max_dd_pct'], 1)} / {fmt_pp(bnh_s['max_dd_pct'], 1)}",
                          help="Största procentuella fall i den tidsviktade utvecklingen, alltså utan att insättningarna döljer fallet.")

                invested_cum = flows.reindex(sv_prices.index).fillna(0.0).cumsum()
                inside = [(n, d, a) for n, d, a in sv_extras if start_ts <= d <= sv_prices.index[-1]]
                # Varje insättning görs första handelsdag på eller efter datumet; samma dag slås ihop.
                trade_day = {n: sv_prices.index[sv_prices.index.searchsorted(d, side="left")] for n, d, _ in inside}
                extra_points = pd.Series({day: 0.0 for day in trade_day.values()}, dtype=float).sort_index()
                for n, _, a in inside:
                    extra_points[trade_day[n]] += a
                point_labels = [", ".join(sv_extra_label[n] for n, _, _ in inside if trade_day[n] == day and sv_extra_label.get(n))
                                for day in extra_points.index]
                st.plotly_chart(charts.build_savings_chart(plan_res["ki"]["equity"], plan_res["bnh"]["equity"], invested_cum,
                                                           extra_points, plan_res["ki"]["weights"]["cash"], point_labels), width="stretch")
                st.caption("Grå yta: insatt kapital. Skillnaden mellan linjerna och den grå ytan är avkastningen. Stjärnor: extra insättningar. "
                           "När KI har sålt placeras nya insättningar enligt modellens aktuella vikter, alltså delvis på räntekontot.")

                with st.expander("År för år"):
                    yr = pd.DataFrame({
                        "Insatt under året": flows.reindex(sv_prices.index).fillna(0.0),
                        "Värde köp och behåll": plan_res["bnh"]["equity"],
                        "Värde KI": plan_res["ki"]["equity"],
                        "twr_bnh": bnh_s["twr"], "twr_ki": ki_s["twr"],
                    })
                    g = yr.groupby(yr.index.year)
                    year_tbl = pd.DataFrame({
                        "År": g.size().index.astype(str),
                        "Insatt under året (kr)": g["Insatt under året"].sum().round(0).to_numpy(),
                        "Insatt totalt (kr)": g["Insatt under året"].sum().cumsum().round(0).to_numpy(),
                        "Värde köp och behåll vid årsslut (kr)": g["Värde köp och behåll"].last().round(0).to_numpy(),
                        "Värde KI vid årsslut (kr)": g["Värde KI"].last().round(0).to_numpy(),
                    })
                    twr_last = yr[["twr_bnh", "twr_ki"]].groupby(yr.index.year).last()
                    twr_prev = twr_last.shift(1)
                    twr_prev.iloc[0] = yr[["twr_bnh", "twr_ki"]].iloc[0].to_numpy()
                    year_tbl["Avkastning köp och behåll (%)"] = ((twr_last["twr_bnh"] / twr_prev["twr_bnh"] - 1) * 100).round(1).to_numpy()
                    year_tbl["Avkastning KI (%)"] = ((twr_last["twr_ki"] / twr_prev["twr_ki"] - 1) * 100).round(1).to_numpy()
                    st.dataframe(year_tbl, width="stretch", hide_index=True)
                    st.caption("Avkastning per år är tidsviktad (påverkas inte av insättningarna). Första och sista året kan vara delår.")

                with st.expander("📖 Hur ska jag läsa siffrorna?"):
                    st.markdown(
                        "**Årsavkastning på insättningarna (pengaviktad, XIRR)** är den årliga avkastning som dina pengar faktiskt fick, "
                        "med hänsyn till när du satte in dem. Satte du in mycket strax före ett ras blir den lägre, strax efter ett ras högre. "
                        "Det är det bästa måttet på hur *din* sparplan gick.\n\n"
                        "**Tidsviktad årsavkastning** mäter strategin oberoende av insättningarna och är jämförbar med CAGR i Portföljbacktestet.\n\n"
                        "**Månadssparande (dollar cost averaging)** betyder att du köper för samma belopp varje månad. När kurserna är låga får du "
                        "fler andelar, vilket jämnar ut inköpspriset.\n\n"
                        "**Antaganden:** insättningen görs på vald dag eller närmast följande handelsdag till dagens stängningskurs. "
                        "Courtage och slippage från Portföljbacktestet dras på aktiedelen av varje insättning (för fonder normalt 0). "
                        "ISK-schablonskatten dras inte; den drabbar båda strategierna ungefär lika. Proxyfondernas avgifter ingår redan i kurserna."
                    )

                with st.expander("Fördjupning – jämför startår"):
                    st.caption("Samma sparplan (startbelopp, månadsbelopp och årlig ökning, men utan extra insättningar) med start i januari varje år "
                               f"och slut {end_ts.date()}. Visar hur mycket starttidpunkten betyder.")
                    if st.checkbox("Kör jämförelsen (tar några sekunder)", False, key="sv_compare_run", help=H("sv_compare")):
                        years = [y for y in range(data_start.year, end_ts.year) if pd.Timestamp(y, 12, 31) < end_ts]
                        rows = []
                        prog = st.progress(0.0)
                        for n_done, y in enumerate(years, start=1):
                            ys = max(pd.Timestamp(y, 1, 1), data_start)
                            yp = fp.loc[ys:end_ts]
                            yplan = dataclasses.replace(plan, start=ys, extra=[])
                            yflows = savings.map_to_trading_days(savings.build_contributions(yplan), yp.index)
                            if len(yp) < 2 or yflows.sum() <= 0:
                                continue
                            yorders = savings_ctx["execution_for"](savings_ctx["ki_signals_monthly"], period_index=yp.index)
                            yres = savings.run_plan(yp, yorders, sv_params, yflows)
                            rows.append({"Startår": str(y),
                                         "Insatt (kr)": round(yres["bnh_summary"]["invested"]),
                                         "Slutvärde köp och behåll (kr)": round(yres["bnh_summary"]["final_value"]),
                                         "Slutvärde KI (kr)": round(yres["ki_summary"]["final_value"]),
                                         "Köp och behåll (%/år)": round(yres["bnh_summary"]["xirr_pct"], 2),
                                         "KI-strategi (%/år)": round(yres["ki_summary"]["xirr_pct"], 2)})
                            prog.progress(n_done / max(len(years), 1))
                        prog.empty()
                        if rows:
                            start_tbl = pd.DataFrame(rows)
                            st.plotly_chart(charts.build_start_year_chart(start_tbl), width="stretch")
                            st.dataframe(start_tbl, width="stretch", hide_index=True)
                            st.caption("%/år = pengaviktad årsavkastning på insättningarna (XIRR). Sena startår har kort sparperiod och påverkas mest av de senaste årens börs.")
                        else:
                            st.info("För kort historik för att jämföra startår.")


# ------------------------------------------------------------
# OM MODELLERNA
# ------------------------------------------------------------
with st.expander("ℹ️ Om modellerna"):
    st.subheader("ℹ️ Om modellerna i appen")
    st.markdown(
        """
Appen innehåller tre principiellt olika angreppssätt, som **inte** ska blandas ihop:

**1. Teknisk RSI/VIX/MACD-modell (flik 1 & 2)**
Kortsiktig, tillgångsspecifik modell som reagerar på pris, momentum och volatilitet för en enskild
ticker. Signaler genereras dagligen och exekveras tidigast nästa handelsdag.

**2. KI/Konjunkturmodellen (flik 3 & 4, samt Månadssparande i flik 5)**
Långsiktig, konträr makromodell baserad på Konjunkturinstitutets Barometerindikator (månadsdata).
Används här som en portföljallokeringsstrategi mellan en bred aktieportfölj och ett räntekonto -
inte som en signal för enskilda aktier.

**3. Buy & Hold**
Passiv referensportfölj med samma målvikter och samma rebalanseringsschema som KI-strategin, men
utan några aktiva allokeringsbeslut. Detta är benchmarken som avgör om KI-modellen historiskt
tillfört något värde utöver att bara äga portföljen rakt av.

Samtliga backtester bygger på historisk data och **garanterar inte** framtida resultat. Se README.md
för fullständig dokumentation av antaganden, datakällor och begränsningar.
        """
    )
