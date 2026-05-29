# FraudLensGov - Plano de Implementacao

Este documento define o plano ponta a ponta para construir o FraudLensGov: um sistema local e auditavel para consumir dados publicos de contratacoes, normalizar itens, construir historico de precos, detectar anomalias e usar RAG/GenAI para explicar alertas sem substituir revisao humana.

## 1. Objetivo

Criar uma plataforma open source que ajude auditores, jornalistas, pesquisadores e equipes de controle social a priorizar analises de licitacoes e compras publicas.

O sistema deve:

- Ingerir dados de PNCP, Compras.gov.br, portais locais e, quando fizer sentido, descoberta via Google Programmable Search.
- Normalizar itens, orgaos, fornecedores, datas, modalidades, quantidades e valores.
- Manter uma base historica comparavel por item, regiao, orgao, fornecedor e data.
- Detectar sinais estatisticos de risco com comparacao historica, vizinhos proximos e clusters.
- Usar RAG/GenAI para explicar o alerta, apontar evidencias e sugerir proximas verificacoes.
- Exibir um dashboard local e gerar relatorio auditavel.

## 2. Fontes de Dados

### PNCP

Uso primario: editais, avisos, atas, contratos e metadados publicados no Portal Nacional de Contratacoes Publicas.

Estrategia:

- Comecar pela API publica de consulta de contratacoes por data de publicacao.
- Tratar publicacoes/objetos de contratacao como `procurement_scope`, nao como item/SKU de preco unitario.
- Persistir o payload bruto junto com o registro normalizado.
- Tratar instabilidade da API com retry, rate limiting e janelas pequenas de data.
- Futuramente, baixar documentos associados ao processo para leitura de edital e termo de referencia.

### Compras.gov.br Dados Abertos

Uso primario: itens, resultados homologados, contratos, fornecedores e pesquisa de precos praticados.

Estrategia:

- Consumir endpoints REST do portal `dadosabertos.compras.gov.br`.
- Para historico pesado, consumir tambem o repositorio CSV oficial anual em `repositorio.dados.gov.br/seges/comprasgov/anual`.
- Priorizar endpoints de resultados de itens para obter valor unitario, quantidade, fornecedor e data.
- Usar endpoints de pesquisa de preco para formar benchmarks por item de catalogo.
- Guardar schema version e endpoint usado para rastreabilidade.

### Portais Locais

Uso primario: municipios, estados, consorcios publicos e autarquias que publicam dados fora de um padrao nacional forte.

Estrategia:

- Criar conectores por familia de portal, nao por cidade isolada.
- Comecar com descoberta de URLs via Google Programmable Search para localizar "licitacoes", "pregao", "dispensa", "contrato", "edital" e "termo de referencia".
- Promover conectores para producao apenas quando houver contrato de dados estavel: API REST, CSV, JSON, RSS ou pagina HTML padronizada.
- Evitar scraping agressivo; respeitar robots.txt, limites de requisicao e termos do portal.

### Google Programmable Search

Uso primario: descoberta e monitoramento de portais locais, nao como fonte primaria de valor/preco.

Estrategia:

- Configurar uma Programmable Search Engine com foco em dominios governamentais.
- Usar `GOOGLE_API_KEY` e `GOOGLE_SEARCH_ENGINE_ID`.
- Persistir apenas metadados de descoberta: titulo, URL, snippet, data da busca e query.
- Transformar resultados recorrentes em conectores dedicados quando houver valor.

## 3. Arquitetura Alvo

Fluxo principal:

```text
PNCP / Compras.gov.br / Portais locais / Google discovery
        |
        v
Bronze Layer: ingestao crua por fonte, janela, endpoint e payload
        |
        v
Silver Layer: normalizacao SQL, enriquecimento PNCP e metadados publicos
        |
        v
Golden Layer: dataset auditavel para comparacao, KNN, alertas e RAG
        |
        v
Base historica de precos e eventos
        |
        v
Motor estatistico de anomalias
        |
        v
RAG + GenAI para explicacao, leitura documental e relatorio
        |
        v
Dashboard local + relatorio auditavel
```

Componentes:

- `sources`: clientes de API e conectores de portais.
- `normalization`: conversao de payloads externos para modelo canonico.
- `storage`: persistencia local, camadas Bronze/Silver/Golden e, depois, adapter Postgres.
- `anomalies`: regras estatisticas explicaveis, outliers e comparacao por vizinhos proximos.
- `rag`: recuperacao de trechos de edital, termo de referencia e historico de precos.
- `genai`: explicacao de alertas via API de modelo configuravel.
- `audit_ui`: dashboard local em Django, APIs JSON operacionais e fila de revisao KNN.

O prototipo ja inclui um modulo RAG local sem dependencias externas para chunking e recuperacao lexical. Ele serve como contrato de arquitetura antes da troca por embeddings.

## 4. Escolha de Tecnologia

### Agora: Python core + Django + SQLite

Motivos:

- Superficie pequena de supply chain: Django 5.2 LTS como dependencia web principal, com versoes exatas.
- Python e adequado para ingestao, estatistica, automacao e integracao com IA.
- SQLite e leve para prototipo local, reproduzivel e facil de versionar em ambiente de desenvolvimento.
- Django entrega rotas, templates, static files, testes de view e uma base natural para evoluir para ORM, admin e autenticacao.
- O core de ingestao, normalizacao, estatistica, clustering, exportacao e RAG prototipo continua em Python de biblioteca padrao.

O Django foi introduzido primeiro como casca de produto: ele le a mesma base SQLite via adapter `Storage`, preservando Bronze/Silver/Golden e evitando uma migracao de dados grande antes de estabilizar o modelo.

### Proxima etapa: Postgres + fila

Quando o volume crescer:

- Django ORM, migrations, admin, autenticacao e permissoes por perfil.
- Postgres para historico, indices, particionamento e consultas analiticas.
- Celery, RQ ou Dramatiq para workers de Bronze, Silver, Golden e RAG.
- Redis ou Postgres como backend de fila conforme o ambiente.
- Django REST Framework apenas quando houver API externa de consumo.
- Playwright apenas se algum portal local exigir navegacao, com isolamento e limites.

O prototipo atual mantem o core em Python puro para reduzir acoplamento, mas os conceitos ja foram separados para migrar naturalmente para apps Django:

- `bronze_records`: captura rapida dos 10 anos sem enriquecimento.
- `procurement_items`: camada Silver normalizada e enriquecida.
- `golden_items`: metadados de qualidade, comparabilidade e materializacao analitica.
- `pipeline_jobs`: progresso observavel com percentual, etapa atual e erro.

O processamento Golden deve ser incremental por padrao. Itens novos ou alterados no Silver sao rematerializados por comparacao entre `procurement_items.inserted_at` e `golden_items.built_at`. Reprocessamento completo deve ser uma operacao explicita (`--full-refresh`) para mudancas de regra, backfills corretivos ou auditoria.

### GraphQL

GraphQL nao deve ser o primeiro passo. Ele pode ser util quando o dashboard tiver muitas visoes agregadas e consumidores externos precisarem compor consultas. Antes disso, REST simples e queries SQL controladas sao mais faceis de auditar.

## 5. Modelo Canonico Inicial

Entidade principal: `ProcurementItem`.

Campos essenciais:

- Identificacao: `source`, `source_record_id`, `procurement_id`, `item_code`.
- Item: `item_description`, `unit`, `quantity`, `unit_price`, `total_value`, `currency`.
- Orgao: `agency_name`, `agency_id`, `city`, `state`.
- Fornecedor: `supplier_name`, `supplier_id`.
- Processo: `procurement_date`, `modality`, `portal_url`.
- Auditoria: `source_payload`, `inserted_at`.

Alerta: `Alert`.

Campos essenciais:

- `risk_type`, `severity`, `score`, `title`, `explanation`.
- `evidence` em JSON.
- `genai_explanation` separada da explicacao deterministica.

## 6. Motor Estatistico, KNN e Clusters

Regras iniciais:

- `price_outlier`: preco unitario acima da mediana de vizinhos proximos comparaveis.
- `supplier_concentration`: mesmo fornecedor vencendo proporcao elevada de registros comparaveis no mesmo orgao.
- `fragmented_purchase`: varios registros do mesmo item, mesmo orgao e mesmo mes somando valor relevante.

Abordagem inicial sem dependencias:

- Tokenizar descricao normalizada do item.
- Calcular similaridade textual simples entre itens.
- Priorizar vizinhos do mesmo estado, unidade e codigo de catalogo quando existirem.
- Normalizar unidades conversiveis antes do benchmark: KG/Tonelada e L/ML entram na mesma base; unidade, pacote e servico so com familia compativel.
- Excluir objetos de edital/contratacao sem item, unidade e quantidade reais de qualquer benchmark de preco.
- Bloquear familias que exigem especificacao tecnica quando nao houver catalogo, complemento ou documento: formulas manipuladas, bundles de refeicao/lanche, sondas/cateteres/proteses e servicos com escopo aberto.
- Comparar preco unitario do item com a mediana dos K vizinhos mais proximos.
- Guardar no alerta quais vizinhos formaram a base de comparacao.

Evolucao com dependencias controladas:

- Usar embeddings para descricao, item de catalogo, unidade e metadados do processo.
- Persistir vetores em Postgres com `pgvector` ou em um indice local versionado.
- Rodar KNN por categoria e regiao antes de calcular outliers.
- Criar clusters de itens/SKUs semanticamente proximos para reduzir ruido de descricoes livres.
- Usar modelos estatisticos robustos: IQR, MAD, isolation forest e regressao por regiao/modalidade quando houver volume.

Regras futuras:

- Distancia de preco por percentil e intervalo interquartil.
- Comparacao por item de catalogo, NCM, CATMAT/CATSER, embeddings e similaridade textual.
- Cluster de fornecedores por socios, endereco, telefone, email e CNAE.
- Prazos anormais entre publicacao, abertura e homologacao.
- Disputa com baixa competitividade.
- Contratos recorrentes perto de limites legais.
- Anomalias por modalidade, regiao e sazonalidade.

## 7. RAG, GenAI e Governanca

O projeto nao deve ser definido como "um app de ChatGPT". O desenho correto e uma camada de inteligencia auditavel que pode usar modelos diferentes, desde que preserve rastreabilidade.

Pipeline RAG proposto:

1. Coletar documentos: edital, termo de referencia, anexos, contrato, ata e aditivos.
2. Extrair texto mantendo pagina, secao, origem e hash do arquivo.
3. Quebrar texto em chunks pequenos com metadados de documento e processo.
4. Gerar embeddings apenas para texto publico e necessario.
5. Recuperar trechos relevantes para cada alerta: item, criterio de julgamento, especificacao, marca, prazo e justificativa.
6. Enviar ao modelo somente o pacote minimo: alerta, estatistica, vizinhos comparaveis e trechos recuperados.
7. Exigir resposta estruturada: fatos, inferencias, hipoteses benignas, riscos e proximos passos.
8. Salvar prompt, modelo, parametros, trechos usados e resposta.

Implementacao incremental:

- Prototipo: chunking local + recuperacao lexical por termos.
- MVP: persistencia de chunks, hashes de documentos e vinculo com alertas.
- Produto: embeddings, KNN vetorial e re-ranking por contexto do processo.
- Operacao: cache de embeddings, custo por fonte e politicas de reprocessamento.

Uso da GenAI:

- Explicar alertas em linguagem clara.
- Ler edital, termo de referencia e anexos quando disponiveis.
- Extrair requisitos, marcas, especificacoes restritivas, prazos e criterios de julgamento.
- Gerar relatorios com evidencias e incertezas.
- Ajudar a normalizar descricoes livres para categorias/SKUs candidatos, sempre com score e revisao humana.
- Persistir sugestoes de categoria/nome canonico com metodo, confianca e evidencias para que a versao RAG preencha o mesmo contrato.

Guardrails:

- Nunca declarar fraude automaticamente.
- Sempre diferenciar fato, inferencia estatistica e hipotese.
- Exigir link ou payload fonte para cada conclusao.
- Registrar prompt, modelo, data e versao da regra.
- Registrar chunks recuperados, hashes e fontes usadas pelo RAG.
- Permitir reprocessamento deterministico sem GenAI.

## 8. Seguranca de Dependencias

Politica atual:

- Django 5.2 LTS como dependencia web principal.
- Dependencias de runtime fixadas com versoes exatas em `requirements.txt`.
- Core de dados mantido sem pacotes externos sempre que a biblioteca padrao for suficiente.
- Variaveis sensiveis somente via `.env` local ou ambiente.
- Nunca commitar chaves.

Ao adicionar novas dependencias:

- Fixar versoes exatas.
- Preferir pacotes amplamente usados e mantidos.
- Usar lockfile (`uv.lock`, `requirements.lock` ou equivalente).
- Rodar auditoria (`pip-audit`, `uv pip audit` ou ferramenta similar).
- Revisar licenca e manutencao.
- Ativar Dependabot/GitHub security alerts.
- Evitar pacotes pequenos para funcoes triviais.

## 9. Roadmap

### Fase 0 - Bootstrap concluido

- Repositorio publico.
- README inicial.
- Core local com baixa dependencia externa e versoes web fixadas.
- Ingestao sample, PNCP, Compras.gov.br e descoberta Google.
- Dashboard local em Django com tema escuro operacional.
- Motor inicial de anomalias.

### Fase 1 - Dados Reais

- Melhorar paginacao e checkpoints por fonte.
- Enriquecer itens Compras.gov.br com descricao de item quando disponivel.
- Criar tabela de execucoes de ingestao.
- Criar Bronze/Silver/Golden com progresso por job.
- Materializar clusters KNN lexicais de itens comparaveis.
- Expor fila KNN separada da fila de alertas, com pares comparaveis e itens bloqueados por qualidade.
- Persistir vizinhos KNN ranqueados por item para explicar agrupamentos.
- Adicionar exportacao CSV/JSON/Markdown de alertas.
- Criar testes de contrato para payloads de PNCP e Compras.gov.br.
- Persistir vizinhos comparaveis usados em cada alerta.
- Bloquear descricoes genericas sem catalogo/complemento em clusters e outliers.

### Fase 2 - Base Historica

- Migrar storage para adapter Postgres mantendo SQLite local.
- Criar indices por item, data, fornecedor, orgao e estado.
- Adicionar deduplicacao robusta.
- Criar snapshots por janela de tempo.

### Fase 3 - Documentos

- Baixar editais e termos de referencia.
- Extrair texto de PDF.
- Relacionar documentos aos itens.
- Criar indice RAG local.
- Usar RAG/GenAI para explicar risco com base no documento e nos vizinhos comparaveis.

### Fase 4 - Produto Local

- Frontend dedicado em React ou HTMX.
- Filtros por estado, orgao, fornecedor, modalidade e severidade.
- Pagina de detalhe do alerta.
- Relatorio auditavel em Markdown/PDF.

### Fase 5 - Operacao

- Jobs agendados.
- Observabilidade.
- Cache HTTP.
- Controle de custo de GenAI.
- Publicacao de datasets derivados sem dados sensiveis.

## 10. Comandos do Prototipo

Carregar dados de exemplo, analisar e abrir dashboard:

```powershell
python -m pip install -r requirements.txt
python -m fraud_lens_gov ingest-sample --analyze --cluster
python -m fraud_lens_gov serve --host 127.0.0.1 --port 8097
```

Ingerir PNCP:

```powershell
python -m fraud_lens_gov ingest-pncp --start 20240501 --end 20240502 --modality 6 --page-size 10 --max-pages 2 --analyze --cluster
```

Ingerir Compras.gov.br:

```powershell
python -m fraud_lens_gov ingest-compras --start 2025-09-01 --end 2025-09-02 --page-size 10 --max-pages 1 --analyze --cluster
```

Rodar o pipeline em camadas:

```powershell
python -m fraud_lens_gov backfill-bronze --source both --start 2016-05-29 --end 2026-05-29 --window-days 30 --max-pages 1 --async
python -m fraud_lens_gov backfill-compras-csv --start-year 2021 --end-year 2026 --limit-per-year 5000 --async
python -m fraud_lens_gov build-silver --source both --async
python -m fraud_lens_gov build-golden --analyze --cluster --categorize --async
```

Para Compras.gov historico, o CSV anual e preferivel ao REST: a documentacao oficial publica diretorios por ano, com arquivos de resultados de itens, itens de contratacoes e contratacoes. A janela real desse conjunto PNCP/Lei 14.133 comeca em 2021; dados anteriores exigem fontes legadas SIASG/Comprasnet ou conectores locais.

Reprocessar tudo apenas quando a regra de qualidade/comparabilidade mudar:

```powershell
python -m fraud_lens_gov build-golden --full-refresh --analyze --cluster --categorize
```

Reconstruir clusters:

```powershell
python -m fraud_lens_gov build-clusters --k 8 --min-similarity 0.42
```

Exportar alertas auditaveis:

```powershell
python -m fraud_lens_gov export-alerts --format md --output reports/alerts.md --limit 25
```

Endpoints locais de investigacao:

```text
GET /api/summary
GET /api/pipeline
GET /api/knn-review
GET /api/clusters/{cluster_id}
GET /api/alerts/{alert_id}
GET /api/items/{item_id}/neighbors
```

Descobrir portais locais via Google:

```powershell
$env:GOOGLE_API_KEY="..."
$env:GOOGLE_SEARCH_ENGINE_ID="..."
python -m fraud_lens_gov discover-portals "portal transparencia licitacoes prefeitura"
```

Gerar explicacoes com OpenAI:

```powershell
$env:OPENAI_API_KEY="..."
python -m fraud_lens_gov explain-alerts --limit 10
```
