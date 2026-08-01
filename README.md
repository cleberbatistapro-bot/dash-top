# Dash Top

Gera dashboards automaticamente a partir de uma planilha (.xlsx/.csv), sem
precisar montar gráfico por gráfico. Você envia o arquivo, escolhe (ou
confirma) a categoria do negócio, revisa o mapeamento das colunas, e o
sistema monta KPIs, gráficos e um relatório em PDF com análise textual —
tudo calculado em cima dos seus dados.

## Como funciona

1. **Upload** — envia uma planilha `.xlsx`, `.xls` ou `.csv`.
2. **Categoria** — o sistema sugere automaticamente a categoria de negócio
   mais provável (Vendas, Financeiro, Estoque, RH, Marketing, Operações ou
   Atendimento) com base nos nomes das colunas.
3. **Mapeamento** — confirma qual coluna da planilha corresponde a cada
   campo esperado pela categoria (data, valor, dimensão etc.).
4. **Dashboard** — KPIs com variação percentual e polaridade, gráfico de
   tendência com agregação adaptativa (dia/semana/mês conforme o período
   filtrado), ranking, composição e filtros por período/dimensão.
5. **Relatório em PDF** — capa, resumo executivo, e uma seção de análise
   escrita (desempenho por dimensão, evolução no período, composição) com
   texto gerado a partir de cálculos reais sobre os dados filtrados — não
   é texto genérico.

## Arquitetura

O motor de dashboards é **genérico**: nenhuma lógica é hardcoded para uma
categoria específica. Cada categoria é um arquivo YAML em
`app/config/categorias/` que declara:

- os campos esperados (`data`, `valor`, dimensões como `vendedor` ou
  `centro_custo`, etc.) e se são obrigatórios;
- os filtros disponíveis;
- as fórmulas dos KPIs (com uma mini-linguagem: `soma(...)`, `media(...)`,
  `contagem(...)`, `contagem_unica(...)`, filtros `onde campo=valor`) e a
  polaridade (se "alta" é positiva, negativa, ou depende do sinal);
- os gráficos de cada versão do dashboard (tendência, ranking, composição
  e, quando fizer sentido, um gráfico derivado tipo "saldo").

Adicionar uma categoria nova é escrever um YAML — o backend
(`dashboard_engine.py`), o frontend e o gerador de PDF já sabem lidar com
qualquer combinação de campos.

## Stack

- **Backend**: FastAPI + pandas, sessões em arquivos JSON (`sessoes/`),
  YAML para configuração de categorias.
- **Frontend**: HTML/CSS/JS puro (sem framework), Chart.js para os
  gráficos, tema claro/escuro.
- **Relatório**: ReportLab para o PDF.

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Acesse `http://127.0.0.1:8000` no navegador.

> No Windows, evite `--reload`: o uvicorn pode deixar um processo filho
> órfão que continua servindo código antigo depois de você matar o
> processo principal.

## Estrutura do projeto

```
app/
  config/categorias/   # um YAML por categoria de negócio
  core/                 # motor do dashboard, matcher de categoria, PDF, análise textual
  models/               # schemas Pydantic
  routers/               # endpoints da API
static/
  etapa1-4.html          # funil: upload → categoria → mapeamento → dashboard
  vendor/                # bibliotecas JS vendorizadas (sem CDN)
```

## Categorias disponíveis

Vendas · Financeiro · Estoque · RH · Marketing · Operações · Atendimento
