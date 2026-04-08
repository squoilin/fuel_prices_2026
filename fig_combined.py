#!/usr/bin/env python3
"""
Combined figure: 65 years of crude + Belgian retail fuel prices + predictions.
All in €2026/litre, with a log-scale "days-before-present" x-axis that
naturally zooms on the Hormuz crisis and ceasefire.

Data sources:
- Crude oil (annual & monthly): FRED — WTI (WTISPLC), Brent (MCOILBRENTEU)
- Crude oil (daily): FRED — Brent (DCOILBRENTEU)
- Crude oil (tick): ICE/broker — BRENTCRUDEOIL_2026-04-08.txt
- Belgian retail fuel prices: beSTAT / Statbel (FOD Economie)
- Belgian CPI: FRED (BELCPIALLMINMEI)
- Exchange rates: FRED (EXUSEU, CCUSMA02BEA618N)
- Regression model: regression_coefficients.csv

Uses matplotlib (Agg backend) to produce a high-quality PNG.
"""

import os, warnings, urllib.request
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.transforms as mtransforms

warnings.filterwarnings("ignore")

# ================================================================
# PATHS & CONSTANTS
# ================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "data")
IMG_DIR    = os.path.join(SCRIPT_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

BBL_TO_L    = 158.987
T_NOW       = pd.Timestamp("2026-04-08 16:00")
EURUSD_APR8 = 1.10

# Estimated Belgian inflation 2025→2026 (~2.1%, consistent with recent trend)
CPI_GROWTH_2026 = 1.021

# Colours
C_CRUDE = "#8e44ab"
C_GAS   = "#e74c3c"
C_DIE   = "#2980b9"
C_HEAT  = "#e67e22"

# ================================================================
# FRED DOWNLOAD UTILITY (caches in DATA_DIR)
# ================================================================
def fetch_fred(series_id, start="1960-01-01"):
    """Download a FRED series as CSV, caching locally. Returns DataFrame."""
    cache = os.path.join(DATA_DIR, f"FRED_{series_id}.csv")
    if not os.path.exists(cache):
        url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv"
               f"?id={series_id}&cosd={start}")
        print(f"  Downloading FRED {series_id} ...")
        urllib.request.urlretrieve(url, cache)
    df = pd.read_csv(cache, parse_dates=["observation_date"])
    df.columns = ["date", series_id]
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna()


# ================================================================
# 1. LOAD ALL DATA
# ================================================================

# --- 1a. beSTAT yearly Belgian retail fuel prices (2006-2026) ----
bestat_yr = pd.read_csv(
    os.path.join(DATA_DIR, "beSTAT_oil_prices_belgium_2006-2026_yearly.csv"),
    encoding="utf-8")
bestat_yr.columns = ["year", "group", "product", "price"]
bestat_yr["price"] = pd.to_numeric(bestat_yr["price"], errors="coerce")

def extract_bestat_yearly(pattern):
    mask = bestat_yr["product"].str.contains(pattern, case=False, na=False)
    s = bestat_yr.loc[mask, ["year", "price"]].dropna()
    return s.drop_duplicates("year").set_index("year")["price"].sort_index()

gas_e10_yr = extract_bestat_yearly(r"Essence 95 RON E10")
gas_e5_yr  = extract_bestat_yearly(r"Essence 95 RON E5")
die_b7_yr  = extract_bestat_yearly(r"Diesel B7")
heat_yr_s  = extract_bestat_yearly(r"Gasoil Diesel Chauffage.*à partir de 2000")

# Gasoline: E10 where available (2014+), E5 fallback for earlier years
gasoline_nom_s = gas_e10_yr.combine_first(gas_e5_yr)
diesel_nom_s   = die_b7_yr
heating_nom_s  = heat_yr_s

years = sorted(set(gasoline_nom_s.index) & set(diesel_nom_s.index)
               & set(heating_nom_s.index))
gasoline_nom_yr = np.array([gasoline_nom_s[y] for y in years])
diesel_nom_yr   = np.array([diesel_nom_s[y] for y in years])
heating_nom_yr  = np.array([heating_nom_s[y] for y in years])
yearly_ts = [pd.Timestamp(f"{y}-07-01") for y in years]

# --- 1b. Historical crude (FRED cached) -------------------------
print("Loading FRED data (cached in data/) ...")
wti     = fetch_fred("WTISPLC",         "1960-01-01")
brent_m = fetch_fred("MCOILBRENTEU",    "1987-01-01")
cpi_be  = fetch_fred("BELCPIALLMINMEI", "1956-01-01")
bef     = fetch_fred("CCUSMA02BEA618N", "1957-01-01")
eur_usd = fetch_fred("EXUSEU",          "1999-01-01")

wti["year"]     = wti.date.dt.year
brent_m["year"] = brent_m.date.dt.year
wti_yr   = wti.groupby("year")["WTISPLC"].mean().rename("crude_usd")
brent_yr = brent_m.groupby("year")["MCOILBRENTEU"].mean().rename("crude_usd")
brent_start = brent_yr.index.min()
crude_usd = pd.concat([wti_yr[wti_yr.index < brent_start], brent_yr])
crude_usd = crude_usd[~crude_usd.index.duplicated(keep="last")].sort_index()
crude_usd[2026] = 95.0

bef["year"] = bef.date.dt.year
fx_pre = bef.groupby("year")["CCUSMA02BEA618N"].mean()
eur_usd["year"] = eur_usd.date.dt.year
fx_post = 1.0 / eur_usd.groupby("year")["EXUSEU"].mean()
fx = pd.concat([fx_pre[fx_pre.index <= 1998], fx_post[fx_post.index >= 1999]])
fx = fx[~fx.index.duplicated(keep="last")].sort_index()
fx[2026] = 1.0 / EURUSD_APR8

cpi_be["year"] = cpi_be.date.dt.year
cpi_yr = cpi_be.groupby("year")["BELCPIALLMINMEI"].mean()
last_cpi_year = cpi_yr.index[cpi_yr.index <= 2025].max()
cpi_yr[2026] = cpi_yr[last_cpi_year] * CPI_GROWTH_2026

hist = pd.DataFrame({"crude_usd": crude_usd}).join(
    pd.DataFrame({"eur_per_usd": fx})).join(
    pd.DataFrame({"cpi_be": cpi_yr}))
hist = hist.dropna()
hist["crude_eur_l"] = (hist["crude_usd"] * hist["eur_per_usd"]) / BBL_TO_L
cpi_2026 = hist.loc[2026, "cpi_be"]
hist["crude_real_eur_l"] = hist["crude_eur_l"] * (cpi_2026 / hist["cpi_be"])
hist = hist.reset_index().rename(columns={"index": "year"})
hist_ts = [pd.Timestamp(f"{int(y)}-07-01") for y in hist["year"]]

# --- Deflate beSTAT yearly retail prices to €2026 ---------------
cpi_arr = np.array([cpi_yr.get(y, np.nan) for y in years])
deflator = cpi_2026 / cpi_arr
gasoline_real_yr = gasoline_nom_yr * deflator
diesel_real_yr   = diesel_nom_yr   * deflator
heating_real_yr  = heating_nom_yr  * deflator

# --- 1c. FRED daily Brent ---------------------------------------
brent_daily = pd.read_csv(
    os.path.join(DATA_DIR, "FRED_DCOILBRENTEU.csv"),
    parse_dates=["observation_date"])
brent_daily.columns = ["date", "brent_usd"]
brent_daily["brent_usd"] = pd.to_numeric(brent_daily["brent_usd"], errors="coerce")
brent_daily = brent_daily.dropna().set_index("date").sort_index()

eur_daily = eur_usd.set_index("date")["EXUSEU"].sort_index()
eur_daily = eur_daily.reindex(
    pd.date_range(eur_daily.index.min(), "2026-04-30", freq="D")).ffill()
eur_daily = eur_daily.fillna(eur_daily.dropna().iloc[-1])

brent_daily["brent_eur"] = brent_daily["brent_usd"] / eur_daily.reindex(brent_daily.index).ffill().bfill().values
brent_daily["brent_eur_l"] = brent_daily["brent_eur"] / BBL_TO_L

cpi_monthly = cpi_be.set_index("date")["BELCPIALLMINMEI"].sort_index()
cpi_d = cpi_monthly.reindex(
    pd.date_range(cpi_monthly.index.min(), "2026-04-30", freq="D")).ffill()
cpi_d = cpi_d.fillna(cpi_d.dropna().iloc[-1])
brent_daily["brent_real_eur_l"] = brent_daily["brent_eur_l"] * (
    cpi_2026 / cpi_d.reindex(brent_daily.index).ffill().bfill().values)

# --- 1d. Tick-level Brent ---------------------------------------
tick_df = pd.read_csv(
    os.path.join(DATA_DIR, "BRENTCRUDEOIL_2026-04-08.txt"),
    sep="\t", encoding="utf-8")
tick_df = tick_df.loc[:, ~tick_df.columns.str.match(r"^Unnamed")]
tick_df.columns = ["datetime_str", "open", "high", "low", "close", "vol", "currency"]
tick_df["datetime"] = pd.to_datetime(tick_df["datetime_str"], format="%d/%m/%Y %H:%M", dayfirst=True)
tick_df["close"] = pd.to_numeric(tick_df["close"], errors="coerce")
tick_df = tick_df.dropna(subset=["close"]).set_index("datetime").sort_index()

tick_5m = tick_df["close"].resample("5min").last().dropna()
tick_5m_eur_l = (tick_5m / EURUSD_APR8) / BBL_TO_L

# --- 1e. beSTAT daily Belgian retail prices ----------------------
daily_raw = pd.read_csv(
    os.path.join(DATA_DIR, "beSTAT_oil_prices_belgium_2025-2026_daily.csv"),
    encoding="utf-8")
daily_raw.columns = ["month_yr", "day_str", "group", "product", "price"]

def parse_bestat_date(row):
    try:
        return pd.to_datetime(row["day_str"], format="%d%b%y")
    except Exception:
        return pd.NaT

daily_raw["date"] = daily_raw.apply(parse_bestat_date, axis=1)
daily_raw = daily_raw.dropna(subset=["date"]).sort_values("date")
daily_raw["price"] = pd.to_numeric(daily_raw["price"], errors="coerce")

def extract_daily(pattern):
    mask = daily_raw["product"].str.contains(pattern, case=False, na=False)
    s = daily_raw.loc[mask, ["date", "price"]].drop_duplicates("date")
    return s.set_index("date")["price"].sort_index()

gas_daily  = extract_daily("Essence 95 RON E10")
die_daily  = extract_daily("Diesel B7")
heat_daily = extract_daily(r"Gasoil chauffage.*à partir de 2000")

# --- 1f. Regression coefficients ---------------------------------
reg_coefs = pd.read_csv(os.path.join(DATA_DIR, "regression_coefficients.csv"))
rc = reg_coefs.set_index("fuel")

gas_int,  gas_slope  = rc.loc["Gasoline E10", "intercept"], rc.loc["Gasoline E10", "slope"]
die_int,  die_slope  = rc.loc["Diesel B7",    "intercept"], rc.loc["Diesel B7",    "slope"]
heat_int, heat_slope = rc.loc["Heating oil",   "intercept"], rc.loc["Heating oil",  "slope"]

gas_int_c,  gas_slope_c  = rc.loc["Gasoline E10", "int_crisis"], rc.loc["Gasoline E10", "slope_crisis"]
die_int_c,  die_slope_c  = rc.loc["Diesel B7",    "int_crisis"], rc.loc["Diesel B7",    "slope_crisis"]
heat_int_c, heat_slope_c = rc.loc["Heating oil",   "int_crisis"], rc.loc["Heating oil",  "slope_crisis"]


# ================================================================
# 2. BUILD PREDICTED FUEL PRICES FROM BRENT
# ================================================================
crisis_start = pd.Timestamp("2026-02-28")
ceasefire    = pd.Timestamp("2026-04-08")

def predict_fuel(brent_eur_bbl, is_crisis):
    if is_crisis:
        return (gas_int_c + gas_slope_c * brent_eur_bbl,
                die_int_c + die_slope_c * brent_eur_bbl,
                heat_int_c + heat_slope_c * brent_eur_bbl)
    else:
        return (gas_int + gas_slope * brent_eur_bbl,
                die_int + die_slope * brent_eur_bbl,
                heat_int + heat_slope * brent_eur_bbl)

# Daily predictions from FRED daily Brent (just last year)
brent_pred = brent_daily.loc["2025-04-01":"2026-04-30"].copy()
brent_pred["is_crisis"] = brent_pred.index >= crisis_start
for idx, row in brent_pred.iterrows():
    g, d, h = predict_fuel(row["brent_eur"], row["is_crisis"])
    brent_pred.loc[idx, "gas_pred"]  = g
    brent_pred.loc[idx, "die_pred"]  = d
    brent_pred.loc[idx, "heat_pred"] = h

# Add tick data daily close for Apr 1-8 2026
tick_daily_close = tick_df["close"].resample("D").last().dropna()
tick_daily_eur = tick_daily_close / EURUSD_APR8
for dt, brent_e in tick_daily_eur.items():
    if dt not in brent_pred.index:
        is_c = dt >= crisis_start
        g, d, h = predict_fuel(brent_e, is_c)
        new_row = pd.Series({
            "brent_usd": brent_e * EURUSD_APR8,
            "brent_eur": brent_e,
            "brent_eur_l": brent_e / BBL_TO_L,
            "brent_real_eur_l": brent_e / BBL_TO_L,
            "is_crisis": is_c,
            "gas_pred": g, "die_pred": d, "heat_pred": h,
        }, name=dt)
        brent_pred = pd.concat([brent_pred, new_row.to_frame().T])
brent_pred = brent_pred.sort_index()


# ================================================================
# 3. UTILITY
# ================================================================
def days_before(ts):
    """Convert to float days before T_NOW. Clamp >= 1 minute."""
    if isinstance(ts, (pd.DatetimeIndex, pd.Series)):
        delta = (T_NOW - ts).total_seconds() / 86400.0
        return delta.clip(lower=1.0 / (24 * 60))
    else:
        delta = (T_NOW - pd.Timestamp(ts)).total_seconds() / 86400.0
        return max(delta, 1.0 / (24 * 60))


# ================================================================
# 4. FIGURE
# ================================================================
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Source Sans Pro", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
})

fig, ax = plt.subplots(figsize=(20, 9))
ax.set_facecolor("#fafbfc")
fig.patch.set_facecolor("white")

Y_TOP = 2.90

# ────────────────────────────────────────────────────────────────
# LAYER 1: Historical crude (annual) — STOP at 1987 where FRED daily begins
# ────────────────────────────────────────────────────────────────
hist_cutoff = hist[hist["year"] <= 1987]
hist_ts_cut = [pd.Timestamp(f"{int(y)}-07-01") for y in hist_cutoff["year"]]
x_hist = np.array([days_before(t) for t in hist_ts_cut])
y_hist = hist_cutoff["crude_real_eur_l"].values
ax.fill_between(x_hist, 0, y_hist, color=C_CRUDE, alpha=0.08, zorder=1)
ax.plot(x_hist, y_hist, color=C_CRUDE, lw=1.3, alpha=0.55, zorder=2,
        label="Crude oil (Brent)")

# ────────────────────────────────────────────────────────────────
# LAYER 2: FRED daily Brent in €2026/l — STOP at Mar 30 (tick data starts Mar 31)
# ────────────────────────────────────────────────────────────────
brent_fred = brent_daily.loc[:"2026-03-30", "brent_real_eur_l"]
brent_pre24 = brent_fred.loc[:"2023-12-31"].resample("W").mean().dropna()
brent_post  = brent_fred.loc["2024-01-01":]
brent_plot  = pd.concat([brent_pre24, brent_post])
x_bd = np.array([days_before(t) for t in brent_plot.index])
# Fill area under FRED daily too (continuous with annual)
ax.fill_between(x_bd[x_bd > 0], 0, brent_plot.values[x_bd > 0],
                color=C_CRUDE, alpha=0.08, zorder=1)
ax.plot(x_bd[x_bd > 0], brent_plot.values[x_bd > 0],
        color=C_CRUDE, lw=0.5, alpha=0.45, zorder=2)

# ────────────────────────────────────────────────────────────────
# LAYER 3: Tick-level Brent (Mar 31–Apr 8) in €2026/l
# ────────────────────────────────────────────────────────────────
# Bridge: connect last FRED daily point to first tick point
last_fred_x = days_before(brent_fred.index[-1])
last_fred_y = brent_fred.iloc[-1]
first_tick_x = days_before(tick_5m_eur_l.index[0])
first_tick_y = tick_5m_eur_l.iloc[0]
ax.plot([last_fred_x, first_tick_x], [last_fred_y, first_tick_y],
        color=C_CRUDE, lw=0.5, alpha=0.45, zorder=2)

# Fill: 5-min grid ffilled
_full_grid = pd.date_range(tick_5m.index[0], tick_5m.index[-1], freq="5min")
_tick_5m_ffill = (tick_5m.reindex(_full_grid).ffill() / EURUSD_APR8) / BBL_TO_L
x_tfill = np.array([days_before(t) for t in _tick_5m_ffill.index])
mask_tfill = x_tfill > 0
x_fill_combined = np.concatenate([[last_fred_x], x_tfill[mask_tfill]])
y_fill_combined = np.concatenate([[last_fred_y], _tick_5m_ffill.values[mask_tfill]])
ax.fill_between(x_fill_combined, 0, y_fill_combined, color=C_CRUDE, alpha=0.08, zorder=1)

# Line: original 5-min tick data
x_tk = np.array([days_before(t) for t in tick_5m_eur_l.index])
ax.plot(x_tk[x_tk > 0], tick_5m_eur_l.values[x_tk > 0],
        color=C_CRUDE, lw=0.7, alpha=0.45, zorder=3)

# ────────────────────────────────────────────────────────────────
# LAYER 4: Belgian retail — YEARLY dots (2006 up to where daily starts)
# ────────────────────────────────────────────────────────────────
daily_start = min(gas_daily.index.min(), die_daily.index.min(), heat_daily.index.min())
yearly_end_idx = max(i for i, t in enumerate(yearly_ts) if t < daily_start)

x_yr = np.array([days_before(t) for t in yearly_ts[:yearly_end_idx + 1]])
for vals, c, lbl in [
    (gasoline_real_yr[:yearly_end_idx + 1], C_GAS,  "Gasoline"),
    (diesel_real_yr[:yearly_end_idx + 1],   C_DIE,  "Diesel"),
    (heating_real_yr[:yearly_end_idx + 1],  C_HEAT, "Heating oil"),
]:
    ax.plot(x_yr, vals, "o-", color=c, lw=1.8, ms=3, alpha=0.7, zorder=5, label=lbl)

# Bridge: connect last yearly point to first daily point
for yr_vals, daily_s, c in [
    (gasoline_real_yr, gas_daily,  C_GAS),
    (diesel_real_yr,   die_daily,  C_DIE),
    (heating_real_yr,  heat_daily, C_HEAT),
]:
    last_yr_x = days_before(yearly_ts[yearly_end_idx])
    last_yr_y = yr_vals[yearly_end_idx]
    first_d_x = days_before(daily_s.index[0])
    first_d_y = daily_s.iloc[0]
    ax.plot([last_yr_x, first_d_x], [last_yr_y, first_d_y],
            color=c, lw=2.0, alpha=0.90, zorder=5)

# ────────────────────────────────────────────────────────────────
# LAYER 5: Belgian retail — DAILY lines, up to ceasefire (Apr 8 00:00)
# ────────────────────────────────────────────────────────────────
fuel_cutoff = pd.Timestamp("2026-04-08")
for s, c in [(gas_daily, C_GAS), (die_daily, C_DIE), (heat_daily, C_HEAT)]:
    s_cut = s.loc[:fuel_cutoff]
    xd = np.array([days_before(t) for t in s_cut.index])
    ax.plot(xd[xd > 0], s_cut.values[xd > 0], color=c, lw=2.0, alpha=0.90, zorder=6)

# ────────────────────────────────────────────────────────────────
# LAYER 6: Regression predictions — continues through Apr 8
# ────────────────────────────────────────────────────────────────
# Normal regime (thin dashed) — pre-crisis
pre_c = brent_pred.loc[brent_pred.index < crisis_start]
x_pc = np.array([days_before(t) for t in pre_c.index])
for col, c in [("gas_pred", C_GAS), ("die_pred", C_DIE), ("heat_pred", C_HEAT)]:
    ax.plot(x_pc, pre_c[col].values, color=c, lw=0.9, alpha=0.30, ls="--", zorder=4)

# Crisis regime (dotted)
cr = brent_pred.loc[(brent_pred.index >= crisis_start) & (brent_pred.index <= ceasefire)]
x_cr = np.array([days_before(t) for t in cr.index])
mask_cr = x_cr > 0

x_apr8_eod = days_before("2026-04-08 12:00")

first = True
for col, c, lbl in [
    ("gas_pred", C_GAS,  "Predicted fuel prices (Brent regression)"),
    ("die_pred", C_DIE,  None),
    ("heat_pred", C_HEAT, None),
]:
    ax.plot(x_cr[mask_cr], cr[col].values[mask_cr],
            color=c, lw=1.3, alpha=0.45, ls=":", zorder=4,
            label=lbl if first else None)
    apr8_val = cr[col].iloc[-1]
    ax.plot([days_before(ceasefire), x_apr8_eod], [apr8_val, apr8_val],
            color=c, lw=1.3, alpha=0.45, ls=":", zorder=4)
    ax.plot(x_apr8_eod, apr8_val, "D",
            color=c, ms=7, zorder=8, markeredgecolor="white", markeredgewidth=0.8)
    first = False

# ────────────────────────────────────────────────────────────────
# EVENT LINES
# ────────────────────────────────────────────────────────────────

# Historical events
hist_events = [
    ("1973-10-01", "Arab embargo"),
    ("1979-01-01", "Iranian rev."),
    ("1986-01-01", "Oil glut"),
    ("1990-08-02", "Gulf War"),
    ("1998-01-01", "Asian crisis"),
    ("2008-07-01", "Financial crisis"),
    ("2014-11-27", "OPEC crash"),
    ("2020-03-09", "COVID"),
    ("2022-02-24", "Ukraine war"),
]

for ds, lbl in hist_events:
    xev = days_before(ds)
    ax.axvline(xev, color="#bbb", lw=0.8, ls="--", alpha=0.55, zorder=0)
    ax.text(xev, 0.50, lbl, ha="left", va="center",
            fontsize=11, color="#666", rotation=90, fontweight="bold",
            transform=mtransforms.blended_transform_factory(ax.transData, ax.transAxes))

# Crisis events
crisis_events = [
    ("2026-02-28", "Strikes begin\n(Feb 28)", "#cc0000"),
    ("2026-04-08", "Ceasefire\n(Apr 8)",      "#008800"),
]
for ds, lbl, clr in crisis_events:
    xev = days_before(ds)
    ax.axvline(xev, color=clr, lw=2.0, ls="--", alpha=0.70, zorder=7)
    ax.text(xev, Y_TOP - 0.05, lbl, ha="center", va="top",
            fontsize=10, color=clr, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=clr, alpha=0.92, lw=0.8),
            zorder=9)

# ────────────────────────────────────────────────────────────────
# AXES FORMATTING
# ────────────────────────────────────────────────────────────────
ax.set_xscale("log")
ax.invert_xaxis()
ax.set_xlim(25000, 0.10)
ax.set_ylim(0, Y_TOP)
ax.yaxis.set_major_locator(mticker.MultipleLocator(0.25))
ax.yaxis.set_minor_locator(mticker.MultipleLocator(0.125))

# Custom x-tick labels — dates, not "days before"
tick_info = [
    ("1960",       "1960-07-01"),
    ("'70",        "1970-07-01"),
    ("'80",        "1980-07-01"),
    ("1990",       "1990-07-01"),
    ("2000",       "2000-07-01"),
    ("2010",       "2010-07-01"),
    ("2020",       "2020-07-01"),
    ("Jan '25",    "2025-01-01"),
    ("Jul '25",    "2025-07-01"),
    ("Jan '26",    "2026-01-01"),
    ("Feb 28",     "2026-02-28"),
    ("Mar 8",      "2026-03-08"),
    ("Mar 19",     "2026-03-19"),
    ("Apr 1",      "2026-04-01"),
    ("Apr 7",      "2026-04-07"),
    ("Apr 8",      "2026-04-08 10:00"),
]

tp = [days_before(d) for _, d in tick_info]
tl = [l for l, _ in tick_info]
ax.set_xticks(tp)
ax.set_xticklabels(tl, fontsize=8)
ax.xaxis.set_minor_locator(mticker.NullLocator())

ax.set_ylabel("€ 2026 / litre", fontsize=13, fontweight="bold")
ax.grid(axis="y", alpha=0.25, lw=0.4)
ax.grid(axis="x", alpha=0.10, lw=0.3)

# ────────────────────────────────────────────────────────────────
# LEGEND
# ────────────────────────────────────────────────────────────────
handles, labels = ax.get_legend_handles_labels()
leg = ax.legend(handles, labels, loc="upper left",
                bbox_to_anchor=(0.0, 1.0),
                fontsize=12, framealpha=0.92, edgecolor="#ccc",
                ncol=2, columnspacing=1.5, handlelength=2.5, borderpad=0.8)

# ────────────────────────────────────────────────────────────────
# TITLE
# ────────────────────────────────────────────────────────────────
ax.set_title(
    "Crude Oil & Belgian Retail Fuel Prices — 1960 to April 8, 2026\n"
    "All in 2026 constant € per litre  ·  Log time axis zooms on the Hormuz crisis",
    fontsize=14, fontweight="bold", color="#2c3e50", pad=14)

# ────────────────────────────────────────────────────────────────
# SAVE
# ────────────────────────────────────────────────────────────────
fig.tight_layout()
out_png = os.path.join(IMG_DIR, "fig_combined_logtime.png")
out_pdf = os.path.join(IMG_DIR, "fig_combined_logtime.pdf")
fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="white")
fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
print(f"Saved: {out_png}")
print(f"Saved: {out_pdf}")
plt.close(fig)
