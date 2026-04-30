# Expected Ranges Online - Arquitetura e Plano

## Objetivo

Disponibilizar um servico online simples para que uma pessoa informe um ativo (ex.: `brl`, `gbp`, `idr`, `aud`) e receba na hora o mesmo conteudo que hoje aparece no `rebalancing_summary`, sem precisar consumir CSV completo.

## Escopo funcional (MVP)

- Entrada:
  - `asset` (obrigatorio)
  - `z_score` (opcional, default `2.576`)
  - `alpha` (opcional, default `0.5`)
  - `horizons` (opcional, default `[2, 7, 14, 30]`)
- Processamento:
  - Buscar historico de preco (online; fallback local opcional)
  - Calcular ranges com a mesma logica atual
  - Regra especial de IDR: usar `price_open` como base de calculo
- Saida:
  - Resumo compacto em JSON (equivalente ao `rebalancing_summary`)
  - Opcional: exibir o texto pronto para copiar/colar no painel

## Arquitetura proposta

### Visao geral

1. **Frontend (painel web)**
   - Formulario simples com seletor de ativo e parametros.
   - Botao "Gerar ranges".
   - Exibe resultado no formato humano (como no summary).

2. **Backend API**
   - Endpoint HTTP para calcular e retornar o resumo.
   - Reutiliza modulo de calculo (core) extraido de `main.py`.
   - Faz fetch de historico de preco via provider (`PolygonIo`) e normaliza dados.

3. **Camada Core (dominio)**
   - Funcoes puras de calculo (`vol`, `expected ranges`, `shifted`, `inverted`, `range_percentage`).
   - Sem dependencia de interface web ou escrita em disco.

4. **Camada Data Provider**
   - Adapter para `PolygonIo`.
   - Retorna DataFrame padronizado (`date`, `price_open`, `price_vwap`, ...).
   - Permite trocar provider futuramente sem mexer no core.

### Tecnologias sugeridas

- **Backend**: FastAPI
- **Frontend**: Streamlit (MVP rapido)  
  - Alternativa: front HTML/JS simples consumindo FastAPI
- **Execucao**: Docker opcional
- **Deploy**:
  - MVP: Render/Railway/Fly.io
  - Producao leve: VPS + Docker + reverse proxy

## Estrutura de pastas sugerida

```text
app/
  api.py                    # FastAPI app / rotas
  schemas.py                # request/response models (Pydantic)
  services/
    expected_ranges.py      # core de calculo (extraido do main.py)
    summary_formatter.py    # transforma resultado em texto estilo summary
  providers/
    polygon_provider.py     # busca historico
  config.py                 # env vars e defaults

ui/
  streamlit_app.py          # painel web

src/
  polygonio.py              # pode permanecer, mas idealmente migrar adapter para app/providers
```

## Contrato da API (proposta)

### POST `/v1/expected-ranges`

Request (exemplo):
```json
{
  "asset": "brl",
  "z_score": 2.576,
  "alpha": 0.5,
  "horizons": [2, 7, 14, 30]
}
```

Response (exemplo resumido):
```json
{
  "asset": "brl",
  "date": "2026-04-01",
  "price_reference": 0.1935,
  "results": [
    {
      "days": 2,
      "range_percentage": 4.82,
      "pair_token_usdc": {"lower": 5.0463, "upper": 5.2955},
      "pair_usdc_token": {"lower": 0.1888, "upper": 0.1981}
    }
  ],
  "summary_text": "..."
}
```

## Regras de negocio importantes

- Ativos aceitos por whitelist (ex.: `brl`, `gbp`, `idr`, `aud`, ...).
- Para `idr`: substituir base de calculo por `price_open`.
- Para demais ativos: usar `price_vwap`.
- Volatilidade: mesma abordagem atual (`std(log_return) * sqrt(365)`).
- Retornar apenas ultima data por horizonte (formato atual do summary).

## Plano de implementacao por etapas

## Fase 1 - Extrair core do `main.py` (baixa-media)

**Objetivo:** separar calculo da camada de script.

Entregaveis:
- `app/services/expected_ranges.py` com funcoes puras:
  - `build_ranges_for_horizon(...)`
  - `build_summary_payload(...)`
- Teste rapido de paridade: resultado igual ao `main.py` para 1 ativo.

Critico:
- Manter compatibilidade da regra de IDR.

## Fase 2 - API FastAPI (media)

**Objetivo:** expor endpoint para calculo online.

Entregaveis:
- `POST /v1/expected-ranges`
- Validacao de request e mensagens de erro claras
- Documentacao Swagger automatica

Critico:
- Timeout e tratamento de falhas do provider.

## Fase 3 - Painel Streamlit (baixa)

**Objetivo:** UX simples para uso manual.

Entregaveis:
- Formulario com ativo + parametros
- Botao de execucao
- Bloco com summary renderizado e botao de copiar

Critico:
- Feedback de loading/erro amigavel.

## Fase 4 - Deploy e operacao (media)

**Objetivo:** colocar no ar com seguranca minima.

Entregaveis:
- Deploy backend + frontend
- Variaveis de ambiente (`API_KEY_POLYGON_IO`, etc.)
- Logs basicos

Critico:
- Proteger endpoint contra abuso (rate limit simples).

## Fase 5 - Robustez (media-alta, opcional)

**Objetivo:** reduzir latencia e falhas.

Entregaveis:
- Cache por ativo+parametros (TTL curto)
- Fallback local JSON quando provider falhar
- Testes automatizados de regressao numerica

## Nivel de dificuldade (resumo)

- **MVP funcional (API + painel):** Media
- **Tempo estimado MVP:** 2 a 5 dias (dependendo de deploy e testes)
- **Producao robusta:** Media/Alta

## Riscos e mitigacoes

- **Dependencia de provider externo:** usar retries + timeout + fallback local.
- **Quebra de compatibilidade numerica:** adicionar testes de snapshot para comparar com output atual.
- **Custos/API limits:** cache e controle de frequencia por usuario.

## O que e necessario para iniciar

1. Definir stack final (FastAPI + Streamlit recomendado).
2. Confirmar lista de ativos suportados inicialmente.
3. Validar contrato de resposta esperado (JSON + texto summary).
4. Provisionar variaveis de ambiente (`API_KEY_POLYGON_IO`).
5. Implementar Fase 1 imediatamente para desacoplar o core.

## Status atual da implementacao

### Entregue nesta iteracao

- Estrutura backend criada em `app/`:
  - `app/api.py` (FastAPI)
  - `app/schemas.py` (request/response)
  - `app/services/expected_ranges.py` (core de calculo + summary_text)
  - `app/providers/history_provider.py` (source `polygon|local|auto`)
  - `app/config.py` (ativos suportados, labels e caminhos)
- Endpoint funcional:
  - `POST /v1/expected-ranges`
  - retorno inclui `summary_text` no formato do `rebalancing_summary`
- Dependencias adicionadas:
  - `fastapi`, `uvicorn`
- `.env.example` adicionado com `API_KEY_POLYGON_IO`
- Smoke test local concluido com sucesso (source `local`).

### Como executar localmente (backend)

```bash
source venv/bin/activate
uvicorn app.api:app --reload
```

Exemplo de request:

```bash
curl -X POST "http://127.0.0.1:8000/v1/expected-ranges" \
  -H "Content-Type: application/json" \
  -d '{"asset":"gbp","source":"local"}'
```

## Proxima iteracao (Fase 3)

- Criar `ui/streamlit_app.py` com:
  - seletor de ativo e parametros
  - botao "Gerar ranges"
  - renderizacao do `summary_text`
  - botao para copiar texto
- Configurar URL do backend via variavel de ambiente da UI.

### Status Fase 3

- `ui/streamlit_app.py` implementado.
- UI chama o endpoint `/v1/expected-ranges` e exibe:
  - `summary_text`
  - payload estruturado
- Botao de teste de conectividade (`/health`) adicionado.
- Botao para baixar `summary_text` em `.txt` adicionado.
- Teste com `source=polygon` concluido com sucesso.

### Ajustes de seguranca (MVP)

- CORS configurado na API via `CORS_ALLOWED_ORIGINS`.
- Rate limit em memoria por IP no endpoint principal:
  - `RATE_LIMIT_REQUESTS` (default: 30)
  - `RATE_LIMIT_WINDOW_SECONDS` (default: 60)

### Como rodar localmente (API + Streamlit)

Terminal 1 (API):
```bash
source venv/bin/activate
uvicorn app.api:app --reload
```

Terminal 2 (UI):
```bash
source venv/bin/activate
streamlit run ui/streamlit_app.py
```

### Variaveis de ambiente

- Backend (API):
  - `API_KEY_POLYGON_IO` (necessaria para `source=polygon`)
  - `CORS_ALLOWED_ORIGINS` (origens permitidas no browser)
  - `RATE_LIMIT_REQUESTS`
  - `RATE_LIMIT_WINDOW_SECONDS`
- Frontend (UI), opcional:
  - `TARGET_PRICE_API_URL` (default: `http://127.0.0.1:8000`)

## Deploy e operacao

Guia pratico de deploy e runbook em:
- `docs/deploy-and-operations.md`

