import json
import os
from typing import Any

import requests


class ClickHouseClient:
    """HTTP client for ClickHouse (expects port-forward on localhost:8123)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int = 120,
    ):
        self.host = host or os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(port or os.getenv("CLICKHOUSE_PORT", "8123"))
        self.user = user or os.getenv("CLICKHOUSE_USER", "default")
        self.password = password or os.getenv("CLICKHOUSE_PASSWORD", "")
        self.timeout = timeout
        self.base_url = f"http://{self.host}:{self.port}/"

    def query_rows(self, sql: str) -> list[dict[str, Any]]:
        sql = sql.strip()
        if "FORMAT" not in sql.upper():
            sql = f"{sql}\nFORMAT JSONEachRow"

        auth = None
        if self.user:
            auth = (self.user, self.password or "")

        response = requests.post(
            self.base_url,
            params={"query": sql},
            auth=auth,
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(
                f"ClickHouse query failed ({response.status_code}): {response.text}"
            )

        rows: list[dict[str, Any]] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def ping(self) -> bool:
        response = requests.get(f"{self.base_url}ping", timeout=10)
        return response.ok and response.text.strip() == "Ok."
