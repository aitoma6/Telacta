# Telacta

Telacta MVP の初期基盤です。現時点では以下を提供します。

- `docker compose up` で起動できるローカル基盤
- Postgres / Neo4j / Cube / FastAPI API コンテナ
- synthetic outdoor sales dataset を Postgres に投入する seed スクリプト

## 構成

- `postgres`: 分析用データ格納先
- `neo4j`: 今後の semantic context graph 用
- `cube`: Postgres 上の sales star schema を公開する semantic layer
- `api`: FastAPI ベースのアプリ API。現時点ではヘルスチェックのみ
- `seed`: synthetic dataset を投入するワンショット実行用サービス

Cube プロジェクトは `cube.dev` の標準的な構成に寄せており、データモデルを `cube/model/cubes/*.yml` に配置しています。

## 前提

- Docker Desktop もしくは Docker Engine
- Docker Compose v2

## 起動手順

1. 基盤を起動します。

```bash
docker compose up --build -d
```

2. synthetic dataset を Postgres に投入します。

```bash
docker compose run --rm seed
```

3. ログや状態を確認します。

```bash
docker compose ps
docker compose logs -f api
```

4. Cube semantic model の一部メタデータを Neo4j に同期します。

```bash
docker compose run --rm sync-metadata
```

`podman compose` を使う場合も同様です。

```bash
podman compose run --rm seed
podman compose run --rm sync-metadata
```

## 接続先

- FastAPI: `http://localhost:8000`
- FastAPI health: `http://localhost:8000/health`
- Cube Playground / API: `http://localhost:4000`
- Neo4j Browser: `http://localhost:7474`
- Postgres: `localhost:5432`

## 動作確認コマンド

API の疎通確認:

```bash
curl http://localhost:8000/health
```

Cube の readiness 確認:

```bash
curl http://localhost:4000/readyz
```

Neo4j へ同期したメタデータ件数の確認:

```bash
docker compose run --rm sync-metadata
```

Cube REST API のメタデータ確認:

```bash
TOKEN=$(python3 - <<'PY'
import base64
import hashlib
import hmac
import json

secret = b"telacta-dev-secret"
header = base64.urlsafe_b64encode(
    json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
).rstrip(b"=")
payload = base64.urlsafe_b64encode(
    json.dumps({"iat": 0, "exp": 4102444800}).encode()
).rstrip(b"=")
signature = base64.urlsafe_b64encode(
    hmac.new(secret, header + b"." + payload, hashlib.sha256).digest()
).rstrip(b"=")
print((header + b"." + payload + b"." + signature).decode())
PY
)

curl -H "Authorization: $TOKEN" http://localhost:4000/cubejs-api/v1/meta
```

Postgres にデータが入ったか確認:

```bash
docker compose exec postgres psql -U telacta -d telacta -c "SELECT COUNT(*) AS fact_rows FROM fact_sales;"
```

商品ライン別売上の簡易確認:

```bash
docker compose exec postgres psql -U telacta -d telacta -c "
SELECT pl.product_line_name, ROUND(SUM(fs.revenue), 2) AS revenue
FROM fact_sales fs
JOIN dim_product p ON fs.product_id = p.product_id
JOIN dim_product_line pl ON p.product_line_id = pl.product_line_id
GROUP BY pl.product_line_name
ORDER BY revenue DESC;
"
```

Neo4j Browser で同期結果を確認:

```cypher
MATCH (c:Cube)-[r]->(n)
RETURN c, r, n
LIMIT 50;
```

BusinessTerm と Synonym の確認:

```cypher
MATCH (s:Synonym)-[:ALIAS_OF]->(t:BusinessTerm)-[:MAPS_TO]->(n)
RETURN s.term, t.term, labels(n), n.full_name
ORDER BY t.term, s.term;
```

## Cube REST API クエリ例

以下は `POST /cubejs-api/v1/load` に対する例です。

JSON と curl の例は [docs/cube-rest-api-examples.md](/Users/aitomahara/dev-work/Telacta/docs/cube-rest-api-examples.md:1) にもまとめています。

2025年の売上:

```bash
curl -X POST http://localhost:4000/cubejs-api/v1/load \
  -H "Content-Type: application/json" \
  -H "Authorization: $TOKEN" \
  --data '{
    "query": {
      "measures": ["sales.total_revenue"],
      "timeDimensions": [
        {
          "dimension": "sales.order_date",
          "dateRange": ["2025-01-01", "2025-12-31"]
        }
      ]
    }
  }'
```

商品ライン別の売上:

```bash
curl -X POST http://localhost:4000/cubejs-api/v1/load \
  -H "Content-Type: application/json" \
  -H "Authorization: $TOKEN" \
  --data '{
    "query": {
      "measures": ["sales.total_revenue"],
      "dimensions": ["products.product_line"],
      "order": {
        "sales.total_revenue": "desc"
      }
    }
  }'
```

国別の売上:

```bash
curl -X POST http://localhost:4000/cubejs-api/v1/load \
  -H "Content-Type: application/json" \
  -H "Authorization: $TOKEN" \
  --data '{
    "query": {
      "measures": ["sales.total_revenue"],
      "dimensions": ["regions.country"],
      "order": {
        "sales.total_revenue": "desc"
      }
    }
  }'
```

直近6ヶ月の売上推移:

```bash
curl -X POST http://localhost:4000/cubejs-api/v1/load \
  -H "Content-Type: application/json" \
  -H "Authorization: $TOKEN" \
  --data '{
    "query": {
      "measures": ["sales.total_revenue"],
      "timeDimensions": [
        {
          "dimension": "sales.order_date",
          "granularity": "month",
          "dateRange": ["2025-07-01", "2025-12-31"]
        }
      ],
      "order": {
        "sales.order_date": "asc"
      }
    }
  }'
```

## データセット概要

seed スクリプトは IBM GO Sales の実データを使わず、完全自作の synthetic outdoor retail dataset を生成します。

- ドメイン: outdoor equipment sales
- 期間: `2024-01-01` から `2025-12-31`
- 主テーブル: `fact_sales`
- ディメンション: `dim_date`, `dim_product`, `dim_product_line`, `dim_retailer`, `dim_region`, `dim_order_method`

## 停止

```bash
docker compose down
```

ボリュームも含めて削除する場合:

```bash
docker compose down -v
```
