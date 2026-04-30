from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import SUPPORTED_ASSETS
from app.providers.history_provider import load_price_history
from app.schemas import ExpectedRangesRequest, ExpectedRangesResponse
from app.services.expected_ranges import compute_expected_ranges, build_summary_payload

app = FastAPI(title="Target Price API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Rate limit simples em memória (por IP), suficiente para MVP único.
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_request_buckets: dict[str, deque[float]] = defaultdict(deque)


def _enforce_rate_limit(client_ip: str) -> None:
    now = time.time()
    bucket = _request_buckets[client_ip]

    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit excedido: máximo de {RATE_LIMIT_REQUESTS} requisições "
                f"a cada {RATE_LIMIT_WINDOW_SECONDS}s."
            ),
        )
    bucket.append(now)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/expected-ranges", response_model=ExpectedRangesResponse)
def expected_ranges(payload: ExpectedRangesRequest, request: Request) -> ExpectedRangesResponse:
    client_ip = request.client.host if request.client else "unknown"
    _enforce_rate_limit(client_ip)

    asset = payload.asset.lower().strip()
    if asset not in SUPPORTED_ASSETS:
        raise HTTPException(status_code=400, detail=f"Ativo não suportado: {asset}")
    if not payload.horizons:
        raise HTTPException(status_code=400, detail="horizons não pode ser vazio")

    try:
        df_history = load_price_history(
            asset=asset, source=payload.source, lookback_days=payload.lookback_days
        )
        results_by_days = compute_expected_ranges(
            asset=asset,
            df_history=df_history,
            horizons=payload.horizons,
            z_score=payload.z_score,
            alpha=payload.alpha,
        )
        response = build_summary_payload(
            asset=asset,
            results_by_days=results_by_days,
            z_score=payload.z_score,
            alpha=payload.alpha,
        )
        return ExpectedRangesResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar expected ranges: {e}")
