# ============================================================
# data.py
# ------------------------------------------------------------
# All nätverksdatahämtning samlas här: kursdata (yfinance),
# valutakurser och KI:s Barometerindikator. Streamlit-cache
# används där den finns tillgänglig, men modulen går även att
# importera och köra helt utan Streamlit (t.ex. i tester) -
# då faller den tillbaka på en enkel in-memory-cache.
#
# Felhantering: nätverksfel loggas tydligt (logging-modulen)
# och fångas ALDRIG tyst med "except Exception: return None"
# utan spårbarhet. Anroparen får ett begripligt None + loggen
# visar tekniska detaljer för felsökning.
# ============================================================

from __future__ import annotations

import functools
import io
import json
import logging
import os
from functools import lru_cache

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from config import FRED_API_URL, FX_TICKER, OECD_CLI_URL, RIKSBANK_API_BASE, RIKSBANK_RATE_SERIES, US_CLI_SERIES

logger = logging.getLogger("simpletradingv3.data")
logging.basicConfig(level=logging.INFO)

try:
    import streamlit as st

    def _cache_data(ttl: int = 3600, show_spinner: str | bool = True):
        return st.cache_data(ttl=ttl, show_spinner=show_spinner)

    _HAS_STREAMLIT = True
except Exception:  # pragma: no cover - miljöer utan streamlit (t.ex. ren pytest)
    _HAS_STREAMLIT = False

    def _cache_data(ttl: int = 3600, show_spinner=True):
        def decorator(func):
            return lru_cache(maxsize=32)(func)

        return decorator


class DataFetchError(Exception):
    """Kastas vid fel som anroparen (UI-lagret) behöver visa begripligt för användaren."""


class _NotCached(Exception):
    """Intern signal: resultatet var None och ska inte sparas i cachen."""


_LAST_ERRORS: dict[str, str] = {}


def last_error(name: str) -> str | None:
    """Senaste felorsak för en datakälla (t.ex. 'us_cli'), för tydligare felmeddelanden i UI."""
    return _LAST_ERRORS.get(name)


def _cache_success(ttl: int = 3600, show_spinner: str | bool = True):
    """Som _cache_data, men ett misslyckat anrop (None) sparas inte: nästa sidladdning försöker igen.

    Tidigare sparades None i upp till ett dygn, så ett tillfälligt fel hos t.ex. KI eller Riksbanken
    låg kvar långt efter att källan fungerade igen.
    """
    def decorator(func):
        def cached(*args, **kwargs):
            result = func(*args, **kwargs)
            if result is None:
                raise _NotCached()
            return result
        cached.__name__ = func.__name__ + "_cached"
        cached.__qualname__ = func.__qualname__ + "_cached"
        cached.__module__ = func.__module__
        cached = _cache_data(ttl=ttl, show_spinner=show_spinner)(cached)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return cached(*args, **kwargs)
            except _NotCached:
                return None

        wrapper.clear = getattr(cached, "clear", None) or getattr(cached, "cache_clear", lambda: None)
        return wrapper
    return decorator


def _flatten_close(raw: pd.DataFrame, column: str = "Close") -> pd.Series:
    """Hanterar yfinance MultiIndex-kolumner robust."""
    if isinstance(raw.columns, pd.MultiIndex):
        return raw[column].iloc[:, 0]
    return raw[column]


def _download(symbol: str, start: str = "2000-01-01") -> pd.DataFrame:
    """Låg-nivå-hämtning med tz-sanering. Kastar DataFetchError vid problem."""
    try:
        raw = yf.download(symbol, start=start, progress=False, auto_adjust=True)
    except Exception as exc:  # nätverksfel, yfinance-internfel etc.
        logger.exception("yfinance-nedladdning misslyckades för %s", symbol)
        raise DataFetchError(f"Kunde inte hämta data för '{symbol}': {exc}") from exc

    if raw is None or raw.empty:
        raise DataFetchError(f"Ingen data returnerades för '{symbol}'. Kontrollera tickern.")

    if raw.index.tz is not None:
        raw.index = raw.index.tz_localize(None)
    return raw


@_cache_success(ttl=3600, show_spinner="Hämtar marknadsdata...")
def fetch_price_series(symbol: str, start: str = "2000-01-01") -> pd.DataFrame | None:
    """
    Hämtar Close (och Open om tillgänglig) för en enskild ticker.
    Returnerar None (och loggar) vid fel, så att UI kan degradera snyggt.
    """
    try:
        raw = _download(symbol, start=start)
    except DataFetchError as exc:
        logger.error(str(exc))
        return None

    df = pd.DataFrame(index=raw.index)
    df["Close"] = _flatten_close(raw, "Close")
    if "Open" in (raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex) else raw.columns):
        df["Open"] = _flatten_close(raw, "Open")
    else:
        df["Open"] = np.nan
    df.dropna(subset=["Close"], inplace=True)
    return df


@_cache_success(ttl=3600, show_spinner="Hämtar VIX...")
def fetch_vix(start: str = "2000-01-01") -> pd.Series | None:
    df = fetch_price_series("^VIX", start=start)
    if df is None:
        return None
    return df["Close"].rename("VIX")


@_cache_success(ttl=3600, show_spinner="Hämtar valutakurs (USD/SEK)...")
def fetch_fx_rate(start: str = "2000-01-01", pair: str = FX_TICKER) -> pd.Series | None:
    df = fetch_price_series(pair, start=start)
    if df is None:
        return None
    return df["Close"].rename("FX")


@_cache_success(ttl=86400, show_spinner="Hämtar Konjunkturbarometer från KI...")
def fetch_ki_barometer() -> pd.DataFrame | None:
    """
    Hämtar Barometerindikatorn via Konjunkturinstitutets PXWeb-API.
    Tidsstämplas till månadens SISTA dag (inte första) för att undvika
    look-ahead bias i nedströms signalberäkning. Se ki_model.py för hur
    en ytterligare publiceringsfördröjning sedan appliceras innan
    informationen anses tillgänglig för handel.
    """
    url = "https://statistik.konj.se/PxWeb/api/v1/sv/KonjBar/indikatorer/Indikatorm.px"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    variable_code = "Indikator"
    target_value_code = "BARTOT"

    try:
        meta_resp = requests.get(url, headers=headers, timeout=10)
        if meta_resp.status_code == 200:
            meta_data = meta_resp.json()
            for var in meta_data.get("variables", []):
                if var.get("code", "").lower() in ("indikator", "contentscode"):
                    variable_code = var.get("code", "Indikator")
                    values = var.get("values", [])
                    value_texts = var.get("valueTexts", [])
                    for val, txt in zip(values, value_texts):
                        if "barometerindikator" in txt.lower():
                            target_value_code = val
                            break
    except Exception:
        logger.warning("Kunde inte läsa KI-metadata, fortsätter med standardkoder.", exc_info=True)

    queries = [
        {
            "query": [{"code": variable_code, "selection": {"filter": "item", "values": [target_value_code]}}],
            "response": {"format": "json"},
        },
        {
            "query": [{"code": variable_code, "selection": {"filter": "all", "values": ["*"]}}],
            "response": {"format": "json"},
        },
    ]

    for query in queries:
        try:
            resp = requests.post(url, json=query, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            logger.warning("KI-API-anrop misslyckades, provar nästa strategi.", exc_info=True)
            continue

        columns = data.get("columns", [])
        data_rows = data.get("data", [])
        if not data_rows:
            continue

        time_col_idx = None
        var_col_idx = 0
        for idx, col in enumerate(columns):
            code_lower = col.get("code", "").lower()
            if code_lower in ("tid", "month", "manad", "månad", "time"):
                time_col_idx = idx
            if code_lower == variable_code.lower():
                var_col_idx = idx
        if time_col_idx is None:
            time_col_idx = 1 if var_col_idx == 0 else 0

        records = []
        for row in data_rows:
            key = row.get("key", [])
            values = row.get("values", [])
            if not key or not values:
                continue
            if query["query"][0]["selection"]["filter"] == "all" and key[var_col_idx] != target_value_code:
                continue

            period_str = key[time_col_idx]
            clean_str = period_str.replace("M", "").replace("-", "").strip()
            try:
                year = int(clean_str[:4])
                month = int(clean_str[4:6])
                # Månadens sista dag - eliminerar look-ahead på dagsnivå.
                period_date = pd.Period(f"{year:04d}-{month:02d}", freq="M").end_time.normalize()
            except (ValueError, IndexError):
                continue

            try:
                value = float(values[0].replace(",", "."))
            except (ValueError, IndexError, TypeError, AttributeError):
                continue

            records.append({"Date": period_date, "Barometer": value})

        if records:
            df_ki = pd.DataFrame(records).sort_values("Date").reset_index(drop=True)
            df_ki.set_index("Date", inplace=True)
            df_ki = df_ki[~df_ki.index.duplicated(keep="last")]
            return df_ki

    logger.error("Kunde inte hämta KI-barometerdata från något av de försökta API-anropen.")
    return None


def parse_riksbank_observations(payload) -> pd.Series:
    """Tolkar SWEA-svaret [{"date": "YYYY-MM-DD", "value": 3.95}, ...] till årsränta i decimalform.

    Riksbanken anger räntan i procent; 3.95 blir 0.0395. Rader utan giltigt värde hoppas över.
    Accepterar även {"observations": [...]} för säkerhets skull.
    """
    if isinstance(payload, dict):
        payload = payload.get("observations") or payload.get("Observations") or []
    rows = []
    for obs in payload or []:
        if not isinstance(obs, dict):
            continue
        date_val = obs.get("date") or obs.get("Date")
        value = obs.get("value", obs.get("Value"))
        try:
            ts = pd.Timestamp(date_val).normalize()
            rate = float(str(value).replace(",", ".")) / 100.0
        except (TypeError, ValueError):
            continue
        if np.isfinite(rate):
            rows.append((ts, rate))
    if not rows:
        return pd.Series(dtype=float, name="Rate")
    s = pd.Series(dict(rows), name="Rate").sort_index()
    return s[~s.index.duplicated(keep="last")]


@_cache_success(ttl=86400, show_spinner="Hämtar historisk ränta från Riksbanken...")
def fetch_riksbank_rate(series_id: str = RIKSBANK_RATE_SERIES, start: str = "1995-01-01") -> pd.Series | None:
    """Daglig svensk kortränta från Riksbankens öppna API (SWEA), som årsränta i decimalform.

    Gratis och utan nyckel (anonymt 5 anrop/minut, 1000/dygn). Ett anrop per dygn tack vare cachen.
    Returnerar None vid fel så att UI kan falla tillbaka på fast ränta.
    """
    end = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    url = f"{RIKSBANK_API_BASE}/Observations/{series_id}/{start}/{end}"
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
    except Exception:
        logger.warning("Riksbankens API kunde inte nås (%s).", url, exc_info=True)
        return None
    if resp.status_code != 200:
        logger.warning("Riksbankens API svarade %s för %s", resp.status_code, url)
        return None
    try:
        series = parse_riksbank_observations(resp.json())
    except ValueError:
        logger.warning("Riksbankens API gav ogiltig JSON för %s", url, exc_info=True)
        return None
    if series.empty:
        logger.warning("Riksbankens API gav inga observationer för %s", series_id)
        return None
    return series


def _month_end(index) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Period(d, freq="M").end_time.normalize() for d in pd.to_datetime(index)])


def parse_oecd_sdmx_csv(text: str) -> pd.Series:
    """Tolkar SDMX-CSV från OECD (kolumner TIME_PERIOD och OBS_VALUE). Månad -> månadens sista dag.

    Om svaret innehåller flera serier väljs den som matchar USA / LI / AA och har flest observationer.
    """
    df = pd.read_csv(io.StringIO(text), dtype=str)
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        raise ValueError("Oväntat format från OECD (saknar TIME_PERIOD/OBS_VALUE).")
    for col, want in (("REF_AREA", "USA"), ("MEASURE", "LI"), ("ADJUSTMENT", "AA"), ("FREQ", "M")):
        if col in df.columns and (df[col] == want).any():
            df = df[df[col] == want]
    dims = [c for c in df.columns if c not in ("TIME_PERIOD", "OBS_VALUE") and df[c].nunique(dropna=False) > 1
            and c.isupper() and not c.startswith("OBS_")]
    if dims:
        best = df.groupby(dims, dropna=False).size().idxmax()
        best = best if isinstance(best, tuple) else (best,)
        for c, v in zip(dims, best):
            df = df[df[c] == v]
    values = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    s = pd.Series(values.to_numpy(), index=_month_end(df["TIME_PERIOD"]), name="CLI").dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_oecd_sdmx_json(payload) -> pd.Series:
    """Tolkar SDMX-JSON från OECD (både 1.0 med 'structure' och 2.0 med 'structures').

    Väljer serien med flest observationer. Tidsdimensionen (TIME_PERIOD) ger månaden.
    """
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    datasets = data.get("dataSets") or []
    structure = data.get("structure") or (data.get("structures") or [None])[0]
    if not datasets or not structure:
        raise ValueError("Oväntat JSON-format från OECD.")
    obs_dims = structure.get("dimensions", {}).get("observation", [])
    time_dim = next((dmn for dmn in obs_dims if dmn.get("id") == "TIME_PERIOD"), obs_dims[0] if obs_dims else None)
    if time_dim is None:
        raise ValueError("OECD-svaret saknar tidsdimension.")
    periods = [v.get("id") for v in time_dim.get("values", [])]
    series_map = datasets[0].get("series") or {}
    if not series_map:
        raise ValueError("OECD-svaret saknar serier.")
    best = max(series_map.values(), key=lambda s: len(s.get("observations", {})))
    rows = []
    for k, vals in best.get("observations", {}).items():
        idx = int(str(k).split(":")[0])
        if idx < len(periods) and vals and vals[0] is not None:
            rows.append((periods[idx], float(vals[0])))
    if not rows:
        return pd.Series(dtype=float, name="CLI")
    s = pd.Series([v for _, v in rows], index=_month_end([p for p, _ in rows]), name="CLI")
    return s[~s.index.duplicated(keep="last")].sort_index()


def parse_fred_observations(payload) -> pd.Series:
    """Tolkar FRED-API:ts JSON {"observations": [{"date": "2026-09-01", "value": "100.99"}, ...]}."""
    obs = (payload or {}).get("observations", [])
    rows = [(o.get("date"), pd.to_numeric(o.get("value"), errors="coerce")) for o in obs if isinstance(o, dict)]
    s = pd.Series([v for _, v in rows], index=_month_end([d for d, _ in rows]) if rows else pd.DatetimeIndex([]), name="CLI", dtype=float)
    s = s.dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _fred_api_key() -> str | None:
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key.strip()
    if _HAS_STREAMLIT:
        try:
            return str(st.secrets["FRED_API_KEY"]).strip()
        except Exception:
            return None
    return None


@_cache_success(ttl=86400, show_spinner="Hämtar OECD:s ledande indikator för USA...")
def fetch_us_cli(series_id: str = US_CLI_SERIES) -> pd.Series | None:
    """OECD:s ledande indikator (CLI) för USA. Först OECD:s öppna API (ingen nyckel), sedan FRED om en
    gratis FRED-nyckel finns. Returnerar None vid fel; orsaken finns i last_error("us_cli")."""
    reasons = []
    attempts = [(OECD_CLI_URL + "&format=csvfile", {}, parse_oecd_sdmx_csv),
                (OECD_CLI_URL + "&format=jsondata", {}, lambda text: parse_oecd_sdmx_json(json.loads(text)))]
    for url, headers, parser in attempts:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 analysverktyg", **headers}, timeout=30)
        except Exception as exc:
            reasons.append(f"OECD kunde inte nås ({type(exc).__name__})")
            logger.warning("OECD-API kunde inte nås (%s).", url, exc_info=True)
            continue
        if resp.status_code != 200:
            reasons.append(f"OECD svarade {resp.status_code}")
            logger.warning("OECD-API svarade %s för %s", resp.status_code, url)
            continue
        try:
            series = parser(resp.text)
        except Exception as exc:
            reasons.append(f"OECD-svaret kunde inte tolkas ({exc})")
            logger.warning("Kunde inte tolka OECD-svaret från %s", url, exc_info=True)
            continue
        if not series.empty:
            _LAST_ERRORS.pop("us_cli", None)
            return series
        reasons.append("OECD gav inga observationer")

    key = _fred_api_key()
    if key:
        try:
            resp = requests.get(FRED_API_URL, params={"series_id": series_id, "api_key": key, "file_type": "json"}, timeout=30)
            if resp.status_code == 200:
                series = parse_fred_observations(resp.json())
                if not series.empty:
                    _LAST_ERRORS.pop("us_cli", None)
                    return series
                reasons.append("FRED gav inga observationer")
            else:
                reasons.append(f"FRED svarade {resp.status_code}")
        except Exception as exc:
            reasons.append(f"FRED kunde inte nås ({type(exc).__name__})")
            logger.warning("FRED-API misslyckades", exc_info=True)
    else:
        reasons.append("ingen FRED-nyckel angiven (valfri reserv)")
    _LAST_ERRORS["us_cli"] = "; ".join(reasons)
    logger.error("OECD CLI för USA kunde inte hämtas: %s", _LAST_ERRORS["us_cli"])
    return None
