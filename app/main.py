import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.services.telacta_tools import (
    answer_bi_question,
    execute_cube_query,
    explain_metric,
    get_cube_query_plan,
    search_semantic_context,
)


app = FastAPI(title="Telacta API", version="0.1.0")


class QuestionRequest(BaseModel):
    question: str


class QueryPlanRequest(BaseModel):
    question: str
    semantic_context: dict[str, Any]


class CubeQueryRequest(BaseModel):
    cube_query: dict[str, Any]


class ExplainMetricRequest(BaseModel):
    metric_name: str


@app.get("/")
def read_root() -> dict[str, str]:
    return {"service": "telacta-api", "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "database_host": os.getenv("DATABASE_URL", "").split("@")[-1],
        "neo4j_uri": os.getenv("NEO4J_URI", ""),
    }


@app.post("/tools/search_semantic_context")
def search_semantic_context_endpoint(request: QuestionRequest) -> dict[str, Any]:
    try:
        return search_semantic_context(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/get_cube_query_plan")
def get_cube_query_plan_endpoint(request: QueryPlanRequest) -> dict[str, Any]:
    try:
        return get_cube_query_plan(request.question, request.semantic_context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/execute_cube_query")
def execute_cube_query_endpoint(request: CubeQueryRequest) -> dict[str, Any]:
    try:
        return execute_cube_query(request.cube_query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/explain_metric")
def explain_metric_endpoint(request: ExplainMetricRequest) -> dict[str, Any]:
    try:
        return explain_metric(request.metric_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/answer_bi_question")
def answer_bi_question_endpoint(request: QuestionRequest) -> dict[str, Any]:
    try:
        return answer_bi_question(request.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
