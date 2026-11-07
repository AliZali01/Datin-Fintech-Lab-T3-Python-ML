
"""Smoke test for the NYC 311 API."""

from data_factory.config import load_config
from data_factory.http_client import HttpClient
from data_factory.exceptions import DataValidationError


def main():
    config = load_config()

    collection = config["collection"]
    scope = collection["scope"]

    conditions = [
        f"created_date >= '{collection['start_date']}'",
        f"created_date < '{collection['end_date']}'",
    ]

    for field in ("agency", "complaint_type", "borough"):
        value = scope.get(field)

        if value is not None and value != "":
            safe_value = str(value).replace("'", "''")
            conditions.append(f"{field} = '{safe_value}'")

    params = {
        "$where": " AND ".join(conditions),
        "$limit": 5,
        "$order": "created_date ASC",
    }

    client = HttpClient.from_config(config)

    rows = client.get(
        config["api"]["endpoint"],
        params=params,
    )

    if not isinstance(rows, list):
        raise DataValidationError(
            "Expected a list of records from NYC 311 API."
        )

    print(f"Records received: {len(rows)}")

    for row in rows:
        print({
            "unique_key": row.get("unique_key"),
            "created_date": row.get("created_date"),
            "complaint_type": row.get("complaint_type"),
            "borough": row.get("borough"),
            "status": row.get("status"),
        })


if __name__ == "__main__":
    main()
