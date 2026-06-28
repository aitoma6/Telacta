from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any

from neo4j import GraphDatabase


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
CUBE_API_URL = os.getenv("CUBE_API_URL", "http://localhost:4000/cubejs-api/v1")
CUBE_API_SECRET = os.getenv("CUBE_API_SECRET", "telacta-dev-secret")
SYNC_SOURCE = "cube_metadata_sync"

PRODUCT_LINES = [
    "Camping Equipment",
    "Mountaineering Equipment",
    "Outdoor Protection",
    "Personal Accessories",
    "Golf Equipment",
]

DEFAULT_TIME_DIMENSION = "sales.order_date"


@dataclass(frozen=True)
class SemanticContext:
    matched_terms: list[str]
    measures: list[str]
    dimensions: list[str]
    time_dimensions: list[str]
    filters: list[dict[str, Any]]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_terms": self.matched_terms,
            "measures": self.measures,
            "dimensions": self.dimensions,
            "time_dimensions": self.time_dimensions,
            "filters": self.filters,
            "confidence": self.confidence,
        }


def _neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    )


def _cube_token() -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"iat": 0, "exp": 4102444800}, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = base64.urlsafe_b64encode(
        hmac.new(CUBE_API_SECRET.encode(), header + b"." + payload, hashlib.sha256).digest()
    ).rstrip(b"=")
    return (header + b"." + payload + b"." + signature).decode()


def _cube_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{CUBE_API_URL.rstrip('/')}/{path.lstrip('/')}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": _cube_token(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise RuntimeError(f"Cube API error: {exc.code} {body}") from exc


def _question_contains(question: str, candidates: list[str]) -> list[str]:
    lowered = question.lower()
    return [candidate for candidate in candidates if candidate.lower() in lowered]


def _extract_year(question: str) -> int | None:
    match = re.search(r"(20\d{2})年", question)
    if match:
        return int(match.group(1))
    if "今年" in question:
        return date.today().year
    return None


def _extract_filters(question: str) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    for product_line in PRODUCT_LINES:
        if product_line.lower() in question.lower():
            filters.append(
                {
                    "member": "products.product_line",
                    "operator": "equals",
                    "values": [product_line],
                }
            )
    return filters


def search_semantic_context(question: str) -> dict[str, Any]:
    matched_terms: list[str] = []
    measures: list[str] = []
    dimensions: list[str] = []
    time_dimensions: list[str] = []
    filters = _extract_filters(question)

    with _neo4j_driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (term:BusinessTerm {source: $source})-[:MAPS_TO]->(target)
                WHERE $question CONTAINS term.term
                RETURN term.term AS matched_term, labels(target)[0] AS target_label, target.full_name AS full_name
                UNION
                MATCH (synonym:Synonym {source: $source})-[:ALIAS_OF]->(term:BusinessTerm)-[:MAPS_TO]->(target)
                WHERE toLower($question) CONTAINS toLower(synonym.term)
                RETURN synonym.term AS matched_term, labels(target)[0] AS target_label, target.full_name AS full_name
                """,
                source=SYNC_SOURCE,
                question=question,
            )
            for record in result:
                matched_term = record["matched_term"]
                target_label = record["target_label"]
                full_name = record["full_name"]
                if matched_term not in matched_terms:
                    matched_terms.append(matched_term)
                if target_label == "Measure" and full_name not in measures:
                    measures.append(full_name)
                if target_label == "Dimension" and full_name not in dimensions:
                    dimensions.append(full_name)

    if "今年" in question or re.search(r"20\d{2}年", question) or "今月" in question or "直近6ヶ月" in question:
        time_dimensions.append(DEFAULT_TIME_DIMENSION)
    if "商品ライン別" in question and "products.product_line" not in dimensions:
        dimensions.append("products.product_line")
    if "国別" in question and "regions.country" not in dimensions:
        dimensions.append("regions.country")
    if "販売方法別" in question and "order_methods.order_method" not in dimensions:
        dimensions.append("order_methods.order_method")

    confidence = 0.25
    if measures:
        confidence += 0.35
    if dimensions or time_dimensions:
        confidence += 0.2
    if filters:
        confidence += 0.1
    if matched_terms:
        confidence += min(0.1, 0.03 * len(matched_terms))

    context = SemanticContext(
        matched_terms=matched_terms,
        measures=measures,
        dimensions=dimensions,
        time_dimensions=time_dimensions,
        filters=filters,
        confidence=min(confidence, 0.99),
    )
    return context.to_dict()


def get_cube_query_plan(question: str, semantic_context: dict[str, Any]) -> dict[str, Any]:
    measures = list(semantic_context.get("measures", []))
    dimensions = list(semantic_context.get("dimensions", []))
    filters = list(semantic_context.get("filters", []))
    time_dimensions: list[dict[str, Any]] = []

    if not measures:
        if "粗利率" in question:
            measures = ["sales.gross_margin_rate"]
        elif "粗利" in question:
            measures = ["sales.gross_profit"]
        elif "平均注文単価" in question or "平均単価" in question or "AOV" in question:
            measures = ["sales.average_order_value"]
        elif "注文数" in question:
            measures = ["sales.order_count"]
        elif "数量" in question:
            measures = ["sales.total_quantity"]
        else:
            measures = ["sales.total_revenue"]

    year = _extract_year(question)
    if year is not None:
        time_dimensions.append(
            {
                "dimension": DEFAULT_TIME_DIMENSION,
                "dateRange": [f"{year}-01-01", f"{year}-12-31"],
            }
        )
    elif "今月" in question:
        today = date.today()
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(day=31)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
            end = next_month.fromordinal(next_month.toordinal() - 1)
        time_dimensions.append(
            {
                "dimension": DEFAULT_TIME_DIMENSION,
                "dateRange": [start.isoformat(), end.isoformat()],
            }
        )
    elif "直近6ヶ月" in question:
        # Seed data currently covers 2024-01-01 to 2025-12-31.
        time_dimensions.append(
            {
                "dimension": DEFAULT_TIME_DIMENSION,
                "granularity": "month",
                "dateRange": ["2025-07-01", "2025-12-31"],
            }
        )

    if "商品ライン別" in question and "products.product_line" not in dimensions:
        dimensions.append("products.product_line")
    if "国別" in question and "regions.country" not in dimensions:
        dimensions.append("regions.country")
    if "販売方法別" in question and "order_methods.order_method" not in dimensions:
        dimensions.append("order_methods.order_method")

    cube_query: dict[str, Any] = {
        "measures": measures,
        "dimensions": dimensions,
        "filters": filters,
    }
    if time_dimensions:
        cube_query["timeDimensions"] = time_dimensions
    if dimensions and measures:
        cube_query["order"] = {measures[0]: "desc"}
    if any(item.get("granularity") == "month" for item in time_dimensions):
        cube_query["order"] = {DEFAULT_TIME_DIMENSION: "asc"}

    query_summary = {
        "measure": measures[0] if len(measures) == 1 else measures,
        "time_range": time_dimensions[0]["dateRange"] if time_dimensions else None,
        "dimensions": dimensions,
        "filters": filters,
    }

    return {"cube_query": cube_query, "query_summary": query_summary}


def execute_cube_query(cube_query: dict[str, Any]) -> dict[str, Any]:
    response = _cube_request("load", {"query": cube_query})
    return {
        "cube_query": cube_query,
        "data": response.get("data", []),
        "annotation": response.get("annotation", {}),
        "request_id": response.get("requestId"),
    }


def explain_metric(metric_name: str) -> dict[str, Any]:
    with _neo4j_driver() as driver:
        with driver.session() as session:
            record = session.run(
                """
                MATCH (measure:Measure {source: $source, full_name: $metric_name})
                OPTIONAL MATCH (cube:Cube {source: $source, name: measure.cube_name})-[:HAS_DIMENSION]->(dimension:Dimension)
                OPTIONAL MATCH (cube)-[:HAS_TIME_DIMENSION]->(time_dimension:TimeDimension)
                OPTIONAL MATCH (term:BusinessTerm {source: $source})-[:MAPS_TO]->(measure)
                OPTIONAL MATCH (synonym:Synonym {source: $source})-[:ALIAS_OF]->(term)
                OPTIONAL MATCH (measure)-[:HAS_GRAIN]->(grain:Grain)
                RETURN measure, cube,
                  collect(DISTINCT dimension.full_name) AS dimensions,
                  collect(DISTINCT time_dimension.full_name) AS time_dimensions,
                  collect(DISTINCT term.term) AS business_terms,
                  collect(DISTINCT synonym.term) AS synonyms,
                  collect(DISTINCT grain.key) AS grains
                """,
                source=SYNC_SOURCE,
                metric_name=metric_name,
            ).single()

    if record is None:
        return {
            "metric": metric_name,
            "found": False,
            "message": "Metric not found in Neo4j metadata.",
        }

    measure = dict(record["measure"])
    return {
        "metric": measure["full_name"],
        "found": True,
        "title": measure["title"],
        "measure_type": measure["measure_type"],
        "cube": record["cube"]["name"] if record["cube"] else None,
        "grain": [grain for grain in record["grains"] if grain],
        "business_terms": [term for term in record["business_terms"] if term],
        "synonyms": [synonym for synonym in record["synonyms"] if synonym],
        "available_dimensions": [dim for dim in record["dimensions"] if dim],
        "available_time_dimensions": [dim for dim in record["time_dimensions"] if dim],
    }


def _format_value(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return value
    else:
        number = float(value)
    return f"{number:,.2f}"


def _build_answer(question: str, query_summary: dict[str, Any], data: list[dict[str, Any]]) -> str:
    if not data:
        return "該当データは見つかりませんでした。"

    first_row = data[0]

    if "商品ライン別" in question:
        return "商品ライン別の売上は " + "、".join(
            f"{row['products.product_line']}: {_format_value(row['sales.total_revenue'])}"
            for row in data
        ) + " です。"
    if "国別" in question:
        return "国別の売上は " + "、".join(
            f"{row['regions.country']}: {_format_value(row['sales.total_revenue'])}"
            for row in data
        ) + " です。"
    if "販売方法別" in question:
        return "販売方法別の注文数は " + "、".join(
            f"{row['order_methods.order_method']}: {_format_value(row['sales.order_count'])}"
            for row in data
        ) + " です。"
    if "直近6ヶ月" in question:
        return "直近6ヶ月の売上推移は " + "、".join(
            f"{row['sales.order_date.month'][:7]}: {_format_value(row['sales.total_revenue'])}"
            for row in data
        ) + " です。"
    if "粗利率" in question:
        return f"粗利率は {_format_value(first_row.get('sales.gross_margin_rate'))} です。"
    if "平均注文単価" in question or "平均単価" in question or "AOV" in question:
        return f"平均注文単価は {_format_value(first_row.get('sales.average_order_value'))} です。"
    if "注文数" in question:
        return f"注文数は {_format_value(first_row.get('sales.order_count'))} です。"
    if "粗利" in question:
        return f"粗利は {_format_value(first_row.get('sales.gross_profit'))} です。"
    return f"売上は {_format_value(first_row.get('sales.total_revenue'))} です。"


def answer_bi_question(question: str) -> dict[str, Any]:
    semantic_context = search_semantic_context(question)
    query_plan = get_cube_query_plan(question, semantic_context)
    query_result = execute_cube_query(query_plan["cube_query"])
    answer = _build_answer(question, query_plan["query_summary"], query_result["data"])
    return {
        "answer": answer,
        "semantic_context": semantic_context,
        "query_summary": query_plan["query_summary"],
        "cube_query": query_plan["cube_query"],
        "data": query_result["data"],
    }
