"""
NarrativeFlow — Market Momentum Radar
======================================
Radar de descubrimiento para detectar cambios de tendencia,
rotación de capital y momentum. No ejecuta operaciones.

Fuentes:
  - yfinance          → Rotación sectorial (ETFs) + precios para filtro
  - ApeWisdom API     → Impulso social / velocidad de menciones
  - Yahoo Finance RSS → Titulares por ticker
  - SPY               → Relative Strength vs. sector

Autor: NarrativeFlow Dev
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import plotly.graph_objects as go
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
import time
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NarrativeFlow",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CSS PERSONALIZADO
# ─────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  /* Base */
  html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
  }

  /* Título principal */
  .nf-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -1px;
    color: #F0F4F8;
    margin-bottom: 0;
  }
  .nf-subtitle {
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 300;
    font-size: 0.85rem;
    color: #8899AA;
    margin-top: 2px;
    letter-spacing: 2px;
    text-transform: uppercase;
  }

  /* Tarjetas métricas custom */
  .metric-card {
    background: linear-gradient(135deg, #0D1117 0%, #161B22 100%);
    border: 1px solid #21262D;
    border-radius: 10px;
    padding: 18px 22px;
    position: relative;
    overflow: hidden;
  }
  .metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: var(--accent, #00D9A3);
    border-radius: 10px 0 0 10px;
  }
  .metric-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #8899AA;
    margin-bottom: 6px;
    font-family: 'IBM Plex Mono', monospace;
  }
  .metric-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #F0F4F8;
    line-height: 1;
  }
  .metric-delta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    margin-top: 5px;
  }
  .delta-pos { color: #00D9A3; }
  .delta-neg { color: #FF4D6D; }
  .delta-neu { color: #8899AA; }

  /* Etiqueta de sección */
  .section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #8899AA;
    border-left: 2px solid #00D9A3;
    padding-left: 8px;
    margin-bottom: 12px;
  }

  /* Noticias en sidebar */
  .news-item {
    background: #0D1117;
    border: 1px solid #21262D;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 0.8rem;
    line-height: 1.4;
  }
  .news-ticker {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #00D9A3;
    font-weight: 600;
    margin-bottom: 2px;
  }
  .news-link {
    color: #C9D1D9;
    text-decoration: none;
  }
  .news-link:hover { color: #00D9A3; }

  /* Tabla dataframe */
  .stDataFrame { border-radius: 8px; overflow: hidden; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #0D1117;
    padding: 4px;
    border-radius: 8px;
  }
  .stTabs [data-baseweb="tab"] {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 1px;
    border-radius: 6px;
    color: #8899AA;
  }
  .stTabs [aria-selected="true"] {
    background: #161B22 !important;
    color: #00D9A3 !important;
  }

  /* Sidebar */
  section[data-testid="stSidebar"] {
    background: #0D1117;
    border-right: 1px solid #21262D;
  }

  /* Warning / info */
  .stAlert { border-radius: 8px; }

  /* Ocultar footer */
  footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────
SECTOR_ETFS = {
    "XLK": "Tecnología",
    "XLF": "Financiero",
    "XLE": "Energía",
    "XLV": "Salud",
    "XLI": "Industrial",
    "XLY": "Consumo Discr.",
    "XLB": "Materiales",
    "XLU": "Utilities",
    "XLRE": "Inmobiliario",
    "XLC": "Comunicación",
}

SECTOR_COLORS = {
    "XLK":  "#00D9A3",
    "XLF":  "#4DA6FF",
    "XLE":  "#FFB347",
    "XLV":  "#FF6B9D",
    "XLI":  "#A78BFA",
    "XLY":  "#F59E0B",
    "XLB":  "#34D399",
    "XLU":  "#60A5FA",
    "XLRE": "#FB923C",
    "XLC":  "#C084FC",
    "SPY":  "#FFFFFF",
}

APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"
YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
BBC_RSS_FALLBACK = "https://feeds.bbci.co.uk/news/business/rss.xml"


# ─────────────────────────────────────────────
# 1. EXTRACCIÓN: ROTACIÓN SECTORIAL
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_sector_rotation(days: int = 30) -> pd.DataFrame:
    """
    Descarga el histórico de ETFs sectoriales + SPY para el período indicado.
    Calcula la variación porcentual acumulada base 0% desde el primer día.
    Incluye columna RS (Relative Strength vs SPY).

    Returns:
        DataFrame con columnas = tickers, índice = fechas, valores = % acum.
        DataFrame vacío si hay error.
    """
    tickers = list(SECTOR_ETFS.keys()) + ["SPY"]
    end = datetime.today()
    start = end - timedelta(days=days + 5)  # margen para fines de semana

    try:
        raw = yf.download(
            tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )["Close"]

        # Asegurar que tengamos exactamente los últimos `days` días de trading
        raw = raw.dropna(how="all").tail(days)

        if raw.empty:
            return pd.DataFrame()

        # Variación acumulada base 0% desde el día 1
        base = raw.iloc[0]
        pct_df = ((raw - base) / base * 100).round(3)

        return pct_df

    except Exception as e:
        st.warning(f"⚠️ Error al descargar datos de yfinance: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# 2. EXTRACCIÓN: PRECIOS ACTUALES (para filtro)
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800)
def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """
    Descarga el precio de cierre más reciente para una lista de tickers.
    Usado para filtrar el rango de precio $15–$150.

    Returns:
        Dict {ticker: precio} — omite tickers con error.
    """
    if not tickers:
        return {}
    try:
        data = yf.download(
            tickers,
            period="2d",
            auto_adjust=True,
            progress=False,
        )["Close"]

        if isinstance(data, pd.Series):
            # Un solo ticker
            return {tickers[0]: float(data.dropna().iloc[-1])} if not data.dropna().empty else {}

        prices = {}
        for t in tickers:
            if t in data.columns:
                series = data[t].dropna()
                if not series.empty:
                    prices[t] = round(float(series.iloc[-1]), 2)
        return prices

    except Exception:
        return {}


# ─────────────────────────────────────────────
# 3. EXTRACCIÓN: IMPULSO SOCIAL (ApeWisdom)
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800)
def fetch_apewisdom(
    price_min: float = 15.0,
    price_max: float = 150.0,
    min_mentions: int = 25,
) -> pd.DataFrame:
    """
    Consulta ApeWisdom API y devuelve el top de tickers ordenado
    por velocidad de crecimiento de menciones en 24h.

    Filtros aplicados:
      - Solo acciones (no crypto)
      - Precio entre price_min y price_max (validado con yfinance)
      - Menciones actuales >= min_mentions (elimina ruido de tickers marginales)
      - Menciones 24h atrás >= min_mentions (el Δ% debe ser sobre una base real)

    Args:
        price_min:    Precio mínimo en $ para el filtro de eficiencia de capital.
        price_max:    Precio máximo en $ para el filtro de eficiencia de capital.
        min_mentions: Umbral mínimo de menciones absolutas. Tickers con menos
                      menciones (hoy O ayer) se descartan como ruido estadístico.

    Returns:
        DataFrame con columnas: Ticker, Menciones, Δ24h%, Rango, Precio
    """
    try:
        resp = requests.get(APEWISDOM_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.warning(f"⚠️ ApeWisdom no disponible: {e}")
        return pd.DataFrame()

    results = data.get("results", [])
    if not results:
        return pd.DataFrame()

    rows = []
    for item in results:
        ticker = item.get("ticker", "").upper().strip()
        mentions = item.get("mentions", 0)
        mentions_24h = item.get("mentions_24h_ago", 0)
        rank = item.get("rank", 0)
        rank_24h = item.get("rank_24h_ago", 0)

        # Filtrar crypto y tickers raros (>5 chars suelen ser índices o errores)
        if not ticker or len(ticker) > 5:
            continue

        # ── Filtro de ruido: exigimos un mínimo de menciones HOY.
        # Las menciones de ayer pueden ser bajas (eso genera el Δ% alto que buscamos).
        # Pero también descartamos casos absurdos: ayer=0 con hoy=2 no es señal.
        # Umbral mínimo en menciones actuales para garantizar base estadística real.
        if mentions < min_mentions:
            continue
        # Descartar también si ayer era 0 o 1 (Δ% matemáticamente inflado sin sentido)
        if mentions_24h < 2:
            continue

        # Calcular velocidad de crecimiento de menciones (Δ%)
        if mentions_24h and mentions_24h > 0:
            delta_pct = round((mentions - mentions_24h) / mentions_24h * 100, 1)
        else:
            delta_pct = 0.0

        rows.append({
            "Ticker": ticker,
            "Menciones": mentions,
            "Menciones 24h atrás": mentions_24h,
            "Δ Menciones 24h %": delta_pct,
            "Rango actual": rank,
            "Rango 24h atrás": rank_24h,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Mantener solo tickers con momentum POSITIVO (el objetivo es señal, no rezagados)
    df = df[df["Δ Menciones 24h %"] > 0]

    # Ordenar por velocidad de crecimiento DESC
    df = df.sort_values("Δ Menciones 24h %", ascending=False).reset_index(drop=True)

    # Tomar top 30 para validar precios (limitamos llamadas a yfinance)
    top_tickers = df["Ticker"].head(30).tolist()
    prices = fetch_prices(top_tickers)

    # Añadir precio y filtrar rango
    df["Precio ($)"] = df["Ticker"].map(prices)
    df = df.dropna(subset=["Precio ($)"])
    df = df[
        (df["Precio ($)"] >= price_min) &
        (df["Precio ($)"] <= price_max)
    ].head(15).reset_index(drop=True)

    df.index += 1  # ranking visual desde 1
    return df


# ─────────────────────────────────────────────
# 4. EXTRACCIÓN: NOTICIAS YAHOO FINANCE RSS
# ─────────────────────────────────────────────
@st.cache_data(ttl=900)
def fetch_yahoo_news(tickers: list[str], max_per_ticker: int = 2) -> list[dict]:
    """
    Consulta el feed RSS de Yahoo Finance para cada ticker.
    Devuelve los titulares más recientes con su URL.

    Args:
        tickers: Lista de tickers a consultar
        max_per_ticker: Máximo de noticias por ticker

    Returns:
        Lista de dicts con keys: ticker, title, link, pubDate
    """
    news = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for ticker in tickers[:10]:  # máximo 10 tickers para no saturar
        url = YAHOO_RSS_URL.format(ticker=ticker)
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                continue

            items = channel.findall("item")
            count = 0
            for item in items:
                if count >= max_per_ticker:
                    break
                title_el = item.find("title")
                link_el  = item.find("link")
                date_el  = item.find("pubDate")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                link  = link_el.text.strip()  if link_el  is not None and link_el.text  else "#"
                pub   = date_el.text.strip()  if date_el  is not None and date_el.text  else ""

                if title:
                    news.append({
                        "ticker":  ticker,
                        "title":   title,
                        "link":    link,
                        "pubDate": pub,
                    })
                    count += 1

        except Exception:
            # Si falla un ticker, continuamos con los demás
            continue

    return news


# ─────────────────────────────────────────────
# 5. GRÁFICO: ROTACIÓN SECTORIAL
# ─────────────────────────────────────────────
def build_rotation_chart(df: pd.DataFrame, show_spy: bool = True) -> go.Figure:
    """
    Construye el gráfico de líneas de rotación sectorial.
    Fondo transparente para heredar el tema de Streamlit.
    """
    fig = go.Figure()

    cols_to_show = [c for c in df.columns if c != "SPY"] if not show_spy else list(df.columns)
    # SPY siempre al final para que esté encima
    if "SPY" in cols_to_show:
        cols_to_show = [c for c in cols_to_show if c != "SPY"] + ["SPY"]

    for ticker in cols_to_show:
        if ticker not in df.columns:
            continue

        is_spy = ticker == "SPY"
        label  = "SPY (Benchmark)" if is_spy else f"{ticker} — {SECTOR_ETFS.get(ticker, ticker)}"
        color  = SECTOR_COLORS.get(ticker, "#AAAAAA")

        fig.add_trace(go.Scatter(
            x=df.index,
            y=df[ticker],
            name=label,
            mode="lines",
            line=dict(
                color=color,
                width=2.5 if is_spy else 1.8,
                dash="dot" if is_spy else "solid",
            ),
            opacity=0.9 if is_spy else 0.75,
            hovertemplate=(
                f"<b>{ticker}</b><br>"
                "%{x|%d %b}<br>"
                "<b>%{y:.2f}%</b><extra></extra>"
            ),
        ))

    # Línea horizontal en 0%
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="rgba(255,255,255,0.2)",
        line_width=1,
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", color="#8899AA", size=11),
        legend=dict(
            bgcolor="rgba(13,17,23,0.8)",
            bordercolor="#21262D",
            borderwidth=1,
            font=dict(size=10),
            orientation="v",
            x=1.01, y=1,
            xanchor="left",
        ),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.05)",
            tickformat="%d %b",
            tickfont=dict(size=10),
            showline=False,
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,0.05)",
            ticksuffix="%",
            tickfont=dict(size=10),
            zeroline=False,
        ),
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=10),
        height=420,
    )

    return fig


# ─────────────────────────────────────────────
# 6. GRÁFICO: RELATIVE STRENGTH BARRAS
# ─────────────────────────────────────────────
def build_rs_chart(df: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras horizontales con la RS de cada sector vs SPY.
    RS = Rendimiento sector - Rendimiento SPY (último día del período).
    """
    if df.empty or "SPY" not in df.columns:
        return go.Figure()

    spy_return = df["SPY"].iloc[-1]
    sectors = [c for c in df.columns if c != "SPY"]

    rs_data = []
    for s in sectors:
        sector_return = df[s].iloc[-1]
        rs = round(sector_return - spy_return, 2)
        rs_data.append({"Sector": f"{s} · {SECTOR_ETFS.get(s, s)}", "RS": rs, "ticker": s})

    rs_df = pd.DataFrame(rs_data).sort_values("RS", ascending=True)

    colors = ["#00D9A3" if v >= 0 else "#FF4D6D" for v in rs_df["RS"]]

    fig = go.Figure(go.Bar(
        x=rs_df["RS"],
        y=rs_df["Sector"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in rs_df["RS"]],
        textposition="outside",
        textfont=dict(family="IBM Plex Mono, monospace", size=10, color="#C9D1D9"),
        hovertemplate="<b>%{y}</b><br>RS vs SPY: <b>%{x:+.2f}%</b><extra></extra>",
    ))

    fig.add_vline(x=0, line_color="rgba(255,255,255,0.2)", line_width=1)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", color="#8899AA", size=11),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.05)",
            ticksuffix="%",
            zeroline=False,
            tickfont=dict(size=9),
        ),
        yaxis=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(size=10),
        ),
        margin=dict(l=10, r=60, t=10, b=10),
        height=340,
        showlegend=False,
    )

    return fig


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def metric_card_html(label: str, value: str, delta: str = "", accent: str = "#00D9A3") -> str:
    delta_class = "delta-pos" if delta.startswith("+") or (delta and delta[0].isdigit()) else "delta-neg" if delta.startswith("-") else "delta-neu"
    delta_html = f'<div class="metric-delta {delta_class}">{delta}</div>' if delta else ""
    return f"""
    <div class="metric-card" style="--accent:{accent}">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value}</div>
      {delta_html}
    </div>
    """


def section_label(text: str) -> None:
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────
def main():

    # ── SIDEBAR ──────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style='padding: 8px 0 20px 0;'>
          <span style='font-family: IBM Plex Mono, monospace; font-size:1.1rem;
                       font-weight:600; color:#F0F4F8;'>⚡ NarrativeFlow</span><br>
          <span style='font-family: IBM Plex Sans, sans-serif; font-size:0.7rem;
                       color:#8899AA; letter-spacing:2px; text-transform:uppercase;'>
            Market Radar v1.0
          </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown('<div class="section-label">Configuración</div>', unsafe_allow_html=True)

        days_range = st.select_slider(
            "Ventana temporal",
            options=[7, 14, 21, 30],
            value=30,
            help="Período para el análisis de rotación sectorial",
        )

        show_spy = st.toggle("Mostrar SPY como benchmark", value=True)

        price_min = st.number_input("Precio mínimo ($)", value=5, min_value=1, max_value=50, step=1)
        price_max = st.number_input("Precio máximo ($)", value=150, min_value=50, max_value=500, step=10)

        min_mentions = st.select_slider(
            "Menciones mínimas hoy",
            options=[5, 10, 15, 20, 25, 50, 100],
            value=10,
            help=(
                "Mínimo de menciones actuales para considerar el ticker. "
                "Las menciones de ayer pueden ser bajas: eso genera el Δ% alto que buscamos. "
                "Sube este valor en días de mucha actividad para reducir ruido."
            ),
        )

        st.markdown("---")

        if st.button("🔄 Refrescar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("""
        <div style='font-size:0.68rem; color:#8899AA; line-height:1.7;'>
          <b style='color:#C9D1D9;'>Fuentes</b><br>
          · yfinance — ETFs sectoriales<br>
          · ApeWisdom — Impulso social<br>
          · Yahoo Finance RSS — Noticias<br><br>
          <b style='color:#C9D1D9;'>Disclaimer</b><br>
          Solo informativo. No constituye asesoramiento financiero.
        </div>
        """, unsafe_allow_html=True)

    # ── CARGA DE DATOS ────────────────────────
    with st.spinner("Cargando datos de mercado..."):
        df_sectors  = fetch_sector_rotation(days=days_range)
        df_momentum = fetch_apewisdom(price_min=float(price_min), price_max=float(price_max), min_mentions=int(min_mentions))

    # ── CABECERA ──────────────────────────────
    st.markdown("""
    <div style='margin-bottom: 24px;'>
      <div class='nf-title'>⚡ NarrativeFlow</div>
      <div class='nf-subtitle'>Market Momentum Radar · Sector Rotation · Social Pulse</div>
    </div>
    """, unsafe_allow_html=True)

    # ── MÉTRICAS DE RESUMEN ───────────────────
    # Calcular valores para las métricas
    leader_ticker, leader_val, leader_delta = "—", "—", ""
    laggard_ticker, laggard_val = "—", "—"
    top_momentum_ticker, top_momentum_delta = "—", "—"

    if not df_sectors.empty:
        last_row = df_sectors.iloc[-1]
        sector_cols = [c for c in last_row.index if c != "SPY"]
        if sector_cols:
            leader_ticker  = last_row[sector_cols].idxmax()
            leader_val_raw = last_row[sector_cols].max()
            leader_val     = f"{leader_val_raw:+.2f}%"
            leader_delta   = f"Último: {leader_val}"
            laggard_ticker = last_row[sector_cols].idxmin()
            laggard_raw    = last_row[sector_cols].min()
            laggard_val    = f"{laggard_raw:+.2f}%"

    if not df_momentum.empty and "Ticker" in df_momentum.columns:
        top_row = df_momentum.iloc[0]
        top_momentum_ticker = top_row["Ticker"]
        top_momentum_delta  = f"+{top_row['Δ Menciones 24h %']:.0f}% menciones"

    # Timestamp siempre en tiempo real (fuera de caché)
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    ts_hora  = now.strftime("%H:%M")
    ts_fecha = now.strftime("%d %b %Y")

    # Auto-refresco cada 5 minutos (300s) — recalcula hora y rerun de Streamlit
    # Usamos un meta-refresh HTML invisible para no añadir dependencias extra
    st.markdown(
        '<meta http-equiv="refresh" content="300">',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card_html(
            "Sector Líder",
            f"{leader_ticker}",
            leader_val,
            "#00D9A3"
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html(
            "Sector Rezagado",
            f"{laggard_ticker}",
            laggard_val,
            "#FF4D6D"
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html(
            "Mayor Momentum Social",
            top_momentum_ticker,
            top_momentum_delta,
            "#4DA6FF"
        ), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card_html(
            "Última Actualización",
            ts_hora,
            ts_fecha,
            "#A78BFA"
        ), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ── TABS PRINCIPALES ─────────────────────
    tab1, tab2, tab3 = st.tabs([
        "📊  Rotación Sectorial",
        "🔥  Momentum Social",
        "📰  Noticias por Ticker",
    ])

    # ── TAB 1: ROTACIÓN SECTORIAL ─────────────
    with tab1:
        if df_sectors.empty:
            st.warning("No se pudieron cargar los datos sectoriales. Intenta refrescar.")
        else:
            col_left, col_right = st.columns([2, 1], gap="large")

            with col_left:
                section_label(f"Rendimiento acumulado · Últimos {days_range} días · Base 0%")
                fig_rotation = build_rotation_chart(df_sectors, show_spy=show_spy)
                st.plotly_chart(fig_rotation, use_container_width=True, config={"displayModeBar": False})

            with col_right:
                section_label("Relative Strength vs SPY")
                fig_rs = build_rs_chart(df_sectors)
                if not fig_rs.data:
                    st.info("Activa el benchmark SPY para ver la Relative Strength.")
                else:
                    st.plotly_chart(fig_rs, use_container_width=True, config={"displayModeBar": False})

            # Tabla de datos al final
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            section_label("Datos — Último día del período")

            last = df_sectors.iloc[-1].drop("SPY", errors="ignore")
            summary_df = pd.DataFrame({
                "ETF":    last.index,
                "Sector": [SECTOR_ETFS.get(t, t) for t in last.index],
                "Δ Acum. %": last.values,
            }).sort_values("Δ Acum. %", ascending=False).reset_index(drop=True)

            if show_spy and "SPY" in df_sectors.columns:
                spy_val = df_sectors["SPY"].iloc[-1]
                summary_df["RS vs SPY"] = (summary_df["Δ Acum. %"] - spy_val).round(3)

            st.dataframe(
                summary_df.style.format({
                    "Δ Acum. %": "{:+.2f}%",
                    "RS vs SPY": "{:+.2f}%",
                }).background_gradient(
                    subset=["Δ Acum. %"],
                    cmap="RdYlGn",
                    vmin=-5, vmax=5,
                ),
                use_container_width=True,
                height=380,
            )

    # ── TAB 2: MOMENTUM SOCIAL ────────────────
    with tab2:
        if df_momentum.empty:
            st.warning("No se pudieron cargar los datos de ApeWisdom. Intenta refrescar.")
        else:
            section_label(f"Top tickers · Filtro precio ${price_min}–${price_max} · Ordenado por Δ menciones 24h")

            # Columnas a mostrar
            display_cols = [
                "Ticker", "Precio ($)", "Menciones",
                "Menciones 24h atrás", "Δ Menciones 24h %", "Rango actual",
            ]
            display_cols = [c for c in display_cols if c in df_momentum.columns]

            styled = df_momentum[display_cols].style.format({
                "Precio ($)": "${:.2f}",
                "Menciones": "{:,.0f}",
                "Menciones 24h atrás": "{:,.0f}",
                "Δ Menciones 24h %": "{:+.1f}%",
            }).background_gradient(
                subset=["Δ Menciones 24h %"],
                cmap="YlOrRd",
            ).set_properties(**{
                "font-family": "IBM Plex Mono, monospace",
                "font-size": "12px",
            })

            st.dataframe(styled, use_container_width=True, height=500)

            st.markdown("""
            <div style='font-size:0.72rem; color:#8899AA; margin-top:8px;'>
              ⚡ <b>Δ Menciones 24h %</b> mide la velocidad de crecimiento de menciones
              (aceleración), no el volumen absoluto. Es la señal más relevante para detectar
              momentum emergente.
            </div>
            """, unsafe_allow_html=True)

    # ── TAB 3: NOTICIAS ───────────────────────
    with tab3:
        # Obtener tickers para las noticias
        news_tickers = []
        if not df_momentum.empty and "Ticker" in df_momentum.columns:
            news_tickers = df_momentum["Ticker"].head(10).tolist()

        if not news_tickers:
            st.info("Carga primero los datos de momentum para ver las noticias por ticker.")
        else:
            with st.spinner("Cargando titulares de Yahoo Finance..."):
                all_news = fetch_yahoo_news(news_tickers, max_per_ticker=2)

            if not all_news:
                st.warning("No se pudieron cargar las noticias. Intenta refrescar.")
            else:
                section_label(f"Titulares recientes · {len(all_news)} noticias · Top {len(news_tickers)} tickers por momentum")

                # Agrupar por ticker para visualización
                by_ticker: dict[str, list] = {}
                for item in all_news:
                    t = item["ticker"]
                    by_ticker.setdefault(t, []).append(item)

                # Mostrar en grid 2 columnas
                tickers_with_news = list(by_ticker.keys())
                left_tickers  = tickers_with_news[::2]
                right_tickers = tickers_with_news[1::2]

                col_n1, col_n2 = st.columns(2, gap="large")

                for ticker_list, col in [(left_tickers, col_n1), (right_tickers, col_n2)]:
                    with col:
                        for ticker in ticker_list:
                            items = by_ticker[ticker]
                            for item in items:
                                title = item["title"]
                                link  = item["link"]
                                pub   = item.get("pubDate", "")[:16] if item.get("pubDate") else ""

                                st.markdown(f"""
                                <div class="news-item">
                                  <div class="news-ticker">▶ {ticker}</div>
                                  <a href="{link}" target="_blank" class="news-link">{title}</a>
                                  <div style="font-size:0.65rem; color:#8899AA; margin-top:4px;">{pub}</div>
                                </div>
                                """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()