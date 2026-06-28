# Cube REST API Examples

Telacta MVP の synthetic sales dataset に対する Cube REST API のクエリ例です。

## 前提

Cube API の認証トークンを生成します。

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
```

## 2025年の売上

Query JSON:

```json
{
  "query": {
    "measures": ["sales.total_revenue"],
    "timeDimensions": [
      {
        "dimension": "sales.order_date",
        "dateRange": ["2025-01-01", "2025-12-31"]
      }
    ]
  }
}
```

curl:

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

## 商品ライン別の売上

Query JSON:

```json
{
  "query": {
    "measures": ["sales.total_revenue"],
    "dimensions": ["products.product_line"],
    "order": {
      "sales.total_revenue": "desc"
    }
  }
}
```

curl:

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

## 国別の売上

Query JSON:

```json
{
  "query": {
    "measures": ["sales.total_revenue"],
    "dimensions": ["regions.country"],
    "order": {
      "sales.total_revenue": "desc"
    }
  }
}
```

curl:

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

## 直近6ヶ月の売上推移

データセットの期間に合わせて、`2025-07-01` から `2025-12-31` を例にしています。

Query JSON:

```json
{
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
}
```

curl:

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
