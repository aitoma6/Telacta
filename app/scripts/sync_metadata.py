from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from neo4j import GraphDatabase


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
CUBE_MODEL_DIR = Path(os.getenv("CUBE_MODEL_DIR", "cube/model/cubes"))
SYNC_SOURCE = "cube_metadata_sync"


BUSINESS_TERM_SEEDS = [
    {
        "term": "売上",
        "maps_to": {"label": "Measure", "key": "sales.total_revenue"},
        "synonyms": ["販売額", "revenue"],
    },
    {
        "term": "数量",
        "maps_to": {"label": "Measure", "key": "sales.total_quantity"},
        "synonyms": ["販売数量", "quantity"],
    },
    {
        "term": "注文数",
        "maps_to": {"label": "Measure", "key": "sales.order_count"},
        "synonyms": ["order count"],
    },
    {
        "term": "平均注文単価",
        "maps_to": {"label": "Measure", "key": "sales.average_order_value"},
        "synonyms": ["平均単価", "AOV"],
    },
    {
        "term": "粗利",
        "maps_to": {"label": "Measure", "key": "sales.gross_profit"},
        "synonyms": [],
    },
    {
        "term": "粗利率",
        "maps_to": {"label": "Measure", "key": "sales.gross_margin_rate"},
        "synonyms": [],
    },
    {
        "term": "地域",
        "maps_to": {"label": "Dimension", "key": "regions.region"},
        "synonyms": [],
    },
    {
        "term": "国",
        "maps_to": {"label": "Dimension", "key": "regions.country"},
        "synonyms": [],
    },
    {
        "term": "商品ライン",
        "maps_to": {"label": "Dimension", "key": "products.product_line"},
        "synonyms": [],
    },
    {
        "term": "販売方法",
        "maps_to": {"label": "Dimension", "key": "order_methods.order_method"},
        "synonyms": [],
    },
]


@dataclass(frozen=True)
class MeasureMetadata:
    cube_name: str
    name: str
    title: str
    full_name: str
    measure_type: str
    grain_key: str


@dataclass(frozen=True)
class DimensionMetadata:
    cube_name: str
    name: str
    title: str
    full_name: str
    dimension_type: str


@dataclass(frozen=True)
class CubeMetadata:
    name: str
    title: str
    measures: list[MeasureMetadata]
    dimensions: list[DimensionMetadata]
    time_dimensions: list[DimensionMetadata]


def titleize(value: str) -> str:
    return value.replace("_", " ").title()


def load_cube_metadata(model_dir: Path) -> list[CubeMetadata]:
    cubes: list[CubeMetadata] = []

    for path in sorted(model_dir.glob("*.yml")):
        payload = yaml.safe_load(path.read_text())
        for cube_def in payload.get("cubes", []):
            cube_name = cube_def["name"]
            cube_title = cube_def.get("title", titleize(cube_name))
            time_dimensions: list[DimensionMetadata] = []
            dimensions: list[DimensionMetadata] = []

            for dimension in cube_def.get("dimensions", []):
                name = dimension["name"]
                dim_type = dimension["type"]
                metadata = DimensionMetadata(
                    cube_name=cube_name,
                    name=name,
                    title=dimension.get("title", titleize(name)),
                    full_name=f"{cube_name}.{name}",
                    dimension_type=dim_type,
                )
                if dim_type == "time":
                    time_dimensions.append(metadata)
                else:
                    dimensions.append(metadata)

            grain_key = (
                time_dimensions[0].full_name if time_dimensions else f"{cube_name}.record"
            )
            measures = [
                MeasureMetadata(
                    cube_name=cube_name,
                    name=measure["name"],
                    title=measure.get("title", titleize(measure["name"])),
                    full_name=f"{cube_name}.{measure['name']}",
                    measure_type=measure["type"],
                    grain_key=grain_key,
                )
                for measure in cube_def.get("measures", [])
            ]

            cubes.append(
                CubeMetadata(
                    name=cube_name,
                    title=cube_title,
                    measures=measures,
                    dimensions=dimensions,
                    time_dimensions=time_dimensions,
                )
            )

    return cubes


def sync_cube_metadata(tx, cubes: list[CubeMetadata]) -> dict[str, int]:
    tx.run("MATCH (n {source: $source}) DETACH DELETE n", source=SYNC_SOURCE)

    cube_count = 0
    measure_count = 0
    dimension_count = 0
    time_dimension_count = 0
    grain_keys: set[str] = set()

    for cube in cubes:
        cube_count += 1
        tx.run(
            """
            CREATE (:Cube {
              source: $source,
              name: $name,
              title: $title
            })
            """,
            source=SYNC_SOURCE,
            name=cube.name,
            title=cube.title,
        )

        for measure in cube.measures:
            measure_count += 1
            grain_keys.add(measure.grain_key)
            tx.run(
                """
                MATCH (cube:Cube {source: $source, name: $cube_name})
                MERGE (grain:Grain {source: $source, key: $grain_key})
                ON CREATE SET grain.name = $grain_name
                CREATE (measure:Measure {
                  source: $source,
                  cube_name: $cube_name,
                  name: $name,
                  title: $title,
                  full_name: $full_name,
                  measure_type: $measure_type
                })
                CREATE (cube)-[:HAS_MEASURE]->(measure)
                CREATE (measure)-[:HAS_GRAIN]->(grain)
                """,
                source=SYNC_SOURCE,
                cube_name=measure.cube_name,
                name=measure.name,
                title=measure.title,
                full_name=measure.full_name,
                measure_type=measure.measure_type,
                grain_key=measure.grain_key,
                grain_name=measure.grain_key.split(".")[-1],
            )

        for dimension in cube.dimensions:
            dimension_count += 1
            tx.run(
                """
                MATCH (cube:Cube {source: $source, name: $cube_name})
                CREATE (dimension:Dimension {
                  source: $source,
                  cube_name: $cube_name,
                  name: $name,
                  title: $title,
                  full_name: $full_name,
                  dimension_type: $dimension_type
                })
                CREATE (cube)-[:HAS_DIMENSION]->(dimension)
                """,
                source=SYNC_SOURCE,
                cube_name=dimension.cube_name,
                name=dimension.name,
                title=dimension.title,
                full_name=dimension.full_name,
                dimension_type=dimension.dimension_type,
            )

        for time_dimension in cube.time_dimensions:
            time_dimension_count += 1
            tx.run(
                """
                MATCH (cube:Cube {source: $source, name: $cube_name})
                MERGE (grain:Grain {source: $source, key: $grain_key})
                ON CREATE SET grain.name = $grain_name
                CREATE (time_dimension:TimeDimension {
                  source: $source,
                  cube_name: $cube_name,
                  name: $name,
                  title: $title,
                  full_name: $full_name,
                  dimension_type: $dimension_type
                })
                CREATE (cube)-[:HAS_TIME_DIMENSION]->(time_dimension)
                """,
                source=SYNC_SOURCE,
                cube_name=time_dimension.cube_name,
                name=time_dimension.name,
                title=time_dimension.title,
                full_name=time_dimension.full_name,
                dimension_type=time_dimension.dimension_type,
                grain_key=time_dimension.full_name,
                grain_name=time_dimension.name,
            )

    for seed in BUSINESS_TERM_SEEDS:
        tx.run(
            f"""
            MATCH (target:{seed["maps_to"]["label"]} {{source: $source, full_name: $target_key}})
            CREATE (term:BusinessTerm {{
              source: $source,
              term: $term
            }})
            CREATE (term)-[:MAPS_TO]->(target)
            """,
            source=SYNC_SOURCE,
            target_key=seed["maps_to"]["key"],
            term=seed["term"],
        )
        for synonym in seed["synonyms"]:
            tx.run(
                """
                MATCH (term:BusinessTerm {source: $source, term: $term})
                CREATE (synonym:Synonym {
                  source: $source,
                  term: $synonym
                })
                CREATE (synonym)-[:ALIAS_OF]->(term)
                """,
                source=SYNC_SOURCE,
                term=seed["term"],
                synonym=synonym,
            )

    return {
        "cubes": cube_count,
        "measures": measure_count,
        "dimensions": dimension_count,
        "time_dimensions": time_dimension_count,
        "grains": len(grain_keys),
        "business_terms": len(BUSINESS_TERM_SEEDS),
        "synonyms": sum(len(seed["synonyms"]) for seed in BUSINESS_TERM_SEEDS),
    }


def main() -> None:
    cubes = load_cube_metadata(CUBE_MODEL_DIR)
    if not cubes:
        raise SystemExit(f"No Cube model files found in {CUBE_MODEL_DIR}")

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    )
    with driver:
        with driver.session() as session:
            stats = session.execute_write(sync_cube_metadata, cubes)

    print(
        "Metadata sync completed. "
        f"cubes={stats['cubes']} "
        f"measures={stats['measures']} "
        f"dimensions={stats['dimensions']} "
        f"time_dimensions={stats['time_dimensions']} "
        f"grains={stats['grains']} "
        f"business_terms={stats['business_terms']} "
        f"synonyms={stats['synonyms']}"
    )


if __name__ == "__main__":
    main()
