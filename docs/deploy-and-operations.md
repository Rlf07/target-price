# Deploy e Operacao - Expected Ranges (API + Streamlit)

## Objetivo

Colocar no ar:
- `target-price-api` (FastAPI)
- `target-price-ui` (Streamlit)

com seguranca basica para uso operacional simples (1 usuario principal, baixa concorrencia).

## Caminho gratuito recomendado (branch `feat/free-streamlit-only`)

Para evitar custo de 2 servicos web, a UI Streamlit agora suporta modo:
- **Direto (gratuito, sem API separada)**  
  Nesse modo, o proprio Streamlit executa o calculo internamente e consulta Polygon sem FastAPI.

### Deploy gratuito sugerido

- **Streamlit Community Cloud** com 1 app:
  - Entry point: `ui/streamlit_app.py`
  - Secrets/vars:
    - `API_KEY_POLYGON_IO` (obrigatoria para `source=polygon`)
  - No app, manter:
    - `Modo de execução` = `Direto (gratuito, sem API separada)`

Esse caminho elimina a necessidade de `target-price-api` e reduz custo para zero (respeitando limites da plataforma e da Polygon).

## Opcao recomendada (simples): Render com Blueprint

Arquivo pronto no repo:
- `render.yaml`

Ele sobe 2 servicos web:
1. API: `uvicorn app.api:app`
2. UI: `streamlit run ui/streamlit_app.py`

## Passo a passo de deploy

1. **Subir o repo atualizado no GitHub** (branch principal).
2. No Render, criar **Blueprint** apontando para o repo.
3. Confirmar os 2 servicos:
   - `target-price-api`
   - `target-price-ui`
4. Definir variaveis de ambiente:

### API (`target-price-api`)
- `API_KEY_POLYGON_IO` = sua chave
- `CORS_ALLOWED_ORIGINS` = URL do frontend (ex.: `https://target-price-ui.onrender.com`)
- `RATE_LIMIT_REQUESTS` = `30`
- `RATE_LIMIT_WINDOW_SECONDS` = `60`

### UI (`target-price-ui`)
- `TARGET_PRICE_API_URL` = URL do backend (ex.: `https://target-price-api.onrender.com`)

5. Deploy.
6. Validar:
   - API health: `GET /health`
   - UI carregando
   - UI gerando summary com `source=polygon`

## Checklist de operacao (runbook)

### Checklist diario (1-2 min)
- API responde `GET /health`
- UI abre sem erro
- 1 request de smoke test (`asset=gbp`) retorna summary

### Alertas / sinais de problema
- HTTP 429 frequente -> aumentar limite ou revisar uso
- HTTP 500 no endpoint principal -> verificar logs de provider/polygon
- Timeout -> reduzir lookback, adicionar retry ou fallback local

### Acoes comuns
- **Troca de chave**: atualizar `API_KEY_POLYGON_IO` no backend e redeploy
- **Ajuste de CORS**: atualizar `CORS_ALLOWED_ORIGINS`
- **Ajuste de limite**: mexer em `RATE_LIMIT_*`

## Custos esperados (uso simples)

O custo total vem de 2 blocos:
1. **Hospedagem** (API + UI)
2. **Dados de mercado (Polygon)**

### 1) Hospedagem

Para esse projeto, o baseline costuma ser:
- 1 instancia pequena para API
- 1 instancia pequena para UI

Em provedores como Render/Railway/Fly, isso geralmente cai em faixa de **baixo custo mensal** para uso simples (single-user / baixa frequencia).  
Se existir free tier no momento, pode iniciar sem custo fixo; se nao, espere custo recorrente por servico.

### 2) Polygon

Depende do plano/limites da sua conta:
- Se seu volume for baixo e o plano atual cobrir, custo marginal pode ser baixo.
- Se exceder limites de requests ou precisar de recursos premium, ha custo adicional.

## Estimativa pratica para o seu caso

Para uso eventual de 1 pessoa:
- **Infra**: tipicamente baixo custo mensal.
- **Polygon**: tende a ser baixo se o numero de chamadas for pequeno.

Em resumo: sim, **pode haver custo**, mas para esse uso a tendencia e ser **baixo**, desde que a frequencia de chamadas fique moderada.

## Hardening (proximos passos)

- Adicionar cache de resposta (TTL 1-5 min) para reduzir chamadas na Polygon.
- Adicionar autenticação simples (token no backend) se URL ficar publica.
- Logs estruturados + monitoramento de erro.
- CI com smoke test do endpoint.
