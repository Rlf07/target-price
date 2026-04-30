import os
import sys
from pathlib import Path

import requests
import streamlit as st

# Garante imports absolutos (app.*) quando streamlit for executado de qualquer diretório.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import DEFAULT_ALPHA, DEFAULT_HORIZONS, DEFAULT_Z_SCORE, SUPPORTED_ASSETS
from app.providers.history_provider import load_price_history
from app.services.expected_ranges import build_summary_payload, compute_expected_ranges


st.set_page_config(page_title="Expected Ranges", page_icon="📈", layout="centered")

st.title("Expected Ranges")
st.caption("Gere ranges por ativo e visualize o summary no formato operacional.")

mode = st.radio(
    "Modo de execução",
    options=["Direto (gratuito, sem API separada)", "Via API (FastAPI)"],
    index=0,
)

default_api_url = os.getenv("TARGET_PRICE_API_URL", "http://127.0.0.1:8000")
api_url = ""
if mode == "Via API (FastAPI)":
    api_url = st.text_input("API base URL", value=default_api_url).rstrip("/")

col1, col2 = st.columns(2)
with col1:
    asset = st.selectbox("Ativo", options=sorted(SUPPORTED_ASSETS), index=sorted(SUPPORTED_ASSETS).index("gbp"))
with col2:
    source = st.selectbox("Fonte de dados", options=["auto", "polygon", "local"], index=0)

col3, col4 = st.columns(2)
with col3:
    z_score = st.number_input("Z-Score", min_value=0.1, value=float(DEFAULT_Z_SCORE), step=0.001, format="%.3f")
with col4:
    alpha = st.number_input("Alpha", min_value=0.0, max_value=1.0, value=float(DEFAULT_ALPHA), step=0.01, format="%.2f")

horizons = st.multiselect(
    "Horizontes (dias)",
    options=[1, 2, 3, 5, 7, 14, 21, 30, 60, 90],
    default=DEFAULT_HORIZONS,
)
lookback_days = st.slider("Lookback (dias)", min_value=90, max_value=2000, value=730, step=30)

test_health = st.button("Testar conexão com API", disabled=mode != "Via API (FastAPI)")
if test_health and mode == "Via API (FastAPI)":
    try:
        health = requests.get(f"{api_url}/health", timeout=10)
        health.raise_for_status()
        st.success(f"API online: {health.json()}")
    except Exception as e:
        st.error(f"Falha no /health: {e}")

run_btn = st.button("Gerar Expected Ranges", type="primary")

if run_btn:
    if not horizons:
        st.warning("Selecione ao menos um horizonte.")
    else:
        payload = {
            "asset": asset,
            "z_score": float(z_score),
            "alpha": float(alpha),
            "horizons": sorted(horizons),
            "source": source,
            "lookback_days": int(lookback_days),
        }
        with st.spinner("Calculando expected ranges..."):
            try:
                if mode == "Via API (FastAPI)":
                    resp = requests.post(f"{api_url}/v1/expected-ranges", json=payload, timeout=60)
                    if resp.status_code >= 400:
                        st.error(f"Erro da API ({resp.status_code}): {resp.text}")
                        st.stop()
                    data = resp.json()
                else:
                    df_history = load_price_history(
                        asset=payload["asset"],
                        source=payload["source"],
                        lookback_days=payload["lookback_days"],
                    )
                    results = compute_expected_ranges(
                        asset=payload["asset"],
                        df_history=df_history,
                        horizons=payload["horizons"],
                        z_score=payload["z_score"],
                        alpha=payload["alpha"],
                    )
                    data = build_summary_payload(
                        asset=payload["asset"],
                        results_by_days=results,
                        z_score=payload["z_score"],
                        alpha=payload["alpha"],
                    )

                st.success(f"Gerado para {data['asset'].upper()} | data base: {data['date']}")

                st.subheader("Summary")
                st.code(data["summary_text"], language="text")
                st.download_button(
                    "Baixar summary (.txt)",
                    data=data["summary_text"],
                    file_name=f"rebalancing_summary_{data['asset']}_z{str(data['z_score']).replace('.', '')}_alpha{int(data['alpha']*100)}.txt",
                    mime="text/plain",
                )

                st.subheader("Resultado estruturado")
                st.json(
                    {
                        "asset": data["asset"],
                        "symbol": data["symbol"],
                        "date": data["date"],
                        "results": data["results"],
                    }
                )
            except Exception as e:
                st.error(f"Falha ao gerar expected ranges: {e}")
