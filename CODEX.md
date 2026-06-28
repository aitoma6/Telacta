# Telacta MVP - Codex Instructions

## Project Goal

Build an MVP for a natural-language BI answering system.

The system should:
1. Accept a business user's text question.
2. Resolve the question against Cube semantic metadata.
3. Use Neo4j as a context graph for semantic search and business term mapping.
4. Generate a Cube REST API query.
5. Execute the Cube REST API query.
6. Return a factual answer with the aggregation conditions used.

This MVP does not include ServiceNow yet.

## Scope

In scope:
- Cube semantic layer
- Neo4j context graph
- Synthetic public sales dataset
- Cube REST API integration
- Basic MCP-compatible tools / API functions
- Japanese business-user questions
- Factual BI questions only

Out of scope for MVP:
- ServiceNow integration
- Decision recommendation
- Root cause analysis
- Advanced forecasting
- Direct SQL generation by LLM
- Tableau or Cognos integration
- Using IBM GO Sales data directly

## Important Design Principles

Cube is the source of truth for semantic model definitions.

Neo4j is not the source of truth.
Neo4j stores a partial graph representation of Cube metadata and business terms to help AI resolve user intent.

The AI must not directly generate SQL against the database.
The AI should generate Cube REST API query JSON.

The answer must include:
- Natural language answer
- Measure used
- Time range used
- Dimensions used
- Filters used
- Cube query JSON used

## Dataset

Use a synthetic public dataset inspired by sales analytics / outdoor retail.

Do not copy IBM Cognos GO Sales sample data.
Do not use proprietary IBM sample data.
Generate original synthetic records.

Domain:
- Outdoor equipment sales

Suggested tables:
- fact_sales
- dim_date
- dim_product
- dim_product_line
- dim_retailer
- dim_region
- dim_order_method

Suggested product lines:
- Camping Equipment
- Mountaineering Equipment
- Outdoor Protection
- Personal Accessories
- Golf Equipment

## Initial BI Questions to Support

Support factual BI questions such as:

- 今年の売上は？
- 2025年の売上は？
- 今月の注文数は？
- 商品ライン別の売上は？
- 国別の売上を教えて
- 販売方法別の注文数は？
- 2025年のCamping Equipmentの売上は？
- 直近6ヶ月の売上推移は？
- 粗利率はいくつ？
- 平均注文単価を教えて

Do not implement "why" analysis yet.

## Core Tools

Implement these tools/functions:

### search_semantic_context

Input:
- natural language question

Output:
- matched business terms
- mapped Cube measures
- mapped Cube dimensions
- candidate filters
- confidence score

### get_cube_query_plan

Input:
- natural language question
- semantic context from Neo4j

Output:
- Cube REST API query JSON
- explanation of selected measure/dimensions/time range/filters

### execute_cube_query

Input:
- Cube REST API query JSON

Output:
- raw Cube API response
- normalized result rows

### explain_metric

Input:
- metric name or business term

Output:
- metric definition
- Cube measure
- available dimensions
- grain
- synonyms

### answer_bi_question

Input:
- natural language question

Output:
- final natural language answer
- query summary
- Cube REST API query JSON
- raw/normalized result

## Neo4j Graph Model

Suggested nodes:
- Cube
- Measure
- Dimension
- TimeDimension
- BusinessTerm
- Synonym
- Grain

Suggested relationships:
- (:Cube)-[:HAS_MEASURE]->(:Measure)
- (:Cube)-[:HAS_DIMENSION]->(:Dimension)
- (:Cube)-[:HAS_TIME_DIMENSION]->(:TimeDimension)
- (:BusinessTerm)-[:MAPS_TO]->(:Measure)
- (:BusinessTerm)-[:MAPS_TO]->(:Dimension)
- (:Synonym)-[:ALIAS_OF]->(:BusinessTerm)
- (:Measure)-[:AVAILABLE_BY]->(:Dimension)
- (:Measure)-[:HAS_GRAIN]->(:Grain)

## Business Terms

Initial mappings:

- 売上, 販売額, revenue -> sales.total_revenue
- 数量, 販売数量, quantity -> sales.total_quantity
- 注文数, order count -> sales.order_count
- 平均注文単価, 平均単価, AOV -> sales.average_order_value
- 粗利 -> sales.gross_profit
- 粗利率 -> sales.gross_margin_rate
- 地域 -> regions.region
- 国 -> regions.country
- 商品ライン -> products.product_line
- 販売方法 -> order_methods.order_method

## Expected Response Format

Return answers in this structure:

{
  "answer": "2025年の売上は 12,345,678 円です。",
  "query_summary": {
    "measure": "sales.total_revenue",
    "time_range": "2025-01-01 to 2025-12-31",
    "dimensions": [],
    "filters": []
  },
  "cube_query": {
    "measures": ["sales.total_revenue"],
    "timeDimensions": [
      {
        "dimension": "sales.order_date",
        "dateRange": ["2025-01-01", "2025-12-31"]
      }
    ]
  }
}

## Implementation Preferences

Prefer:
- Python for orchestration / API layer
- FastAPI for local API
- Docker Compose for Postgres, Cube, Neo4j
- Seed scripts for synthetic data
- Clear README
- Tests for query planning and semantic mapping

Avoid:
- Hard-coding all answers
- Direct SQL generation by LLM
- Hidden assumptions
- Proprietary sample data
- Overbuilding ServiceNow-related features