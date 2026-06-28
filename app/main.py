import os

from fastapi import FastAPI


app = FastAPI(title="Telacta API", version="0.1.0")


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
