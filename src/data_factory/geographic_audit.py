
import csv
import json
import math
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

import requests
from shapely import points, covers
from shapely.geometry import shape

from .exceptions import DataValidationError


BOUNDARY_URL = (
    "https://data.cityofnewyork.us/api/v3/"
    "views/gthc-hcne/query.geojson?accessType=DOWNLOAD"
)

BOROUGHS = {
    "BRONX",
    "BROOKLYN",
    "MANHATTAN",
    "QUEENS",
    "STATEN ISLAND",
}


def download_boundary_file(path):

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print("Using existing boundary file.")
        return path

    print("Downloading NYC borough boundaries...")

    try:
        response = requests.get(
            BOUNDARY_URL,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

    except (requests.RequestException, ValueError) as exc:
        raise DataValidationError(
            f"Boundary download failed: {exc}"
        ) from exc

    if payload.get("type") != "FeatureCollection":
        raise DataValidationError(
            "Invalid boundary GeoJSON."
        )

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    return path


def load_boundaries(path):

    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise DataValidationError(
            f"Cannot read boundary file: {exc}"
        ) from exc

    geometries = {}

    for feature in payload.get("features", []):

        properties = {
            str(k).lower(): v
            for k, v in feature.get("properties", {}).items()
        }

        name = str(
            properties.get("boroname", "")
        ).strip().upper()

        if name not in BOROUGHS:
            continue

        if name in geometries:
            raise DataValidationError(
                f"Duplicate boundary: {name}"
            )

        geometry = shape(feature["geometry"])

        if geometry.is_empty or not geometry.is_valid:
            raise DataValidationError(
                f"Invalid geometry: {name}"
            )

        geometries[name] = geometry

    if set(geometries) != BOROUGHS:
        raise DataValidationError(
            f"Expected five boroughs, found: {list(geometries)}"
        )

    bounds = [
        geometry.bounds
        for geometry in geometries.values()
    ]

    min_lon = min(b[0] for b in bounds)
    min_lat = min(b[1] for b in bounds)
    max_lon = max(b[2] for b in bounds)
    max_lat = max(b[3] for b in bounds)

    if not (
        -75.5 < min_lon < -72.5
        and -75.5 < max_lon < -72.5
        and 39.5 < min_lat < 42
        and 39.5 < max_lat < 42
    ):
        raise DataValidationError(
            "Unexpected boundary coordinate system."
        )

    return geometries


def parse_coordinate(value):

    if value is None or not str(value).strip():
        return None, "missing"

    try:
        number = float(value)
    except (ValueError, TypeError):
        return None, "invalid"

    if not math.isfinite(number):
        return None, "invalid"

    return number, "valid"


def normalize_borough(value):

    if value is None:
        return ""

    return str(value).strip().upper()


def run_geographic_audit(
    cases_path,
    boundary_path,
    output_path,
    report_path,
    chunk_size=25000,
):

    geometries = load_boundaries(boundary_path)

    cases_path = Path(cases_path)
    output_path = Path(output_path)
    report_path = Path(report_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total = 0
    valid_coordinates = 0
    missing_coordinates = 0
    partial_coordinates = 0
    invalid_coordinates = 0
    outside_boundary = 0
    ambiguous_boundary = 0

    compared = 0
    matches = 0
    mismatches = 0

    unspecified = 0
    inferable_unspecified = 0
    invalid_source_borough = 0

    source_counts = Counter()
    spatial_counts = Counter()
    mismatch_pairs = Counter()
    inferable_by_borough = Counter()

    with (
        cases_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as source,
        output_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as output
    ):

        reader = csv.DictReader(source)

        required = {
            "unique_key",
            "created_date",
            "incident_zip",
            "borough",
            "latitude",
            "longitude",
        }

        if not required.issubset(reader.fieldnames or []):
            raise DataValidationError(
                "Required geographic columns are missing."
            )

        fields = [
            "unique_key",
            "created_date",
            "incident_zip",
            "source_borough",
            "spatial_borough",
            "latitude",
            "longitude",
            "discrepancy_type",
        ]

        writer = csv.DictWriter(
            output,
            fieldnames=fields,
        )
        writer.writeheader()

        while True:

            rows = []

            for _ in range(chunk_size):
                row = next(reader, None)

                if row is None:
                    break

                rows.append(row)

            if not rows:
                break

            total += len(rows)

            valid_indices = []
            lons = []
            lats = []

            for i, row in enumerate(rows):

                lat, lat_status = parse_coordinate(
                    row.get("latitude")
                )

                lon, lon_status = parse_coordinate(
                    row.get("longitude")
                )

                if (
                    lat_status == "missing"
                    and lon_status == "missing"
                ):
                    missing_coordinates += 1
                    continue

                if (
                    lat_status == "missing"
                    or lon_status == "missing"
                ):
                    partial_coordinates += 1
                    continue

                if (
                    lat_status != "valid"
                    or lon_status != "valid"
                    or not -90 <= lat <= 90
                    or not -180 <= lon <= 180
                ):
                    invalid_coordinates += 1
                    continue

                valid_coordinates += 1

                valid_indices.append(i)
                lats.append(lat)
                lons.append(lon)

            spatial_names = [None] * len(rows)

            if valid_indices:

                point_array = points(lons, lats)

                hit_counts = [
                    0
                ] * len(valid_indices)

                assigned_names = [
                    None
                ] * len(valid_indices)

                for borough, geometry in geometries.items():

                    mask = covers(
                        geometry,
                        point_array,
                    )

                    for j, hit in enumerate(mask):

                        if hit:
                            hit_counts[j] += 1
                            assigned_names[j] = borough

                for j, row_index in enumerate(valid_indices):

                    if hit_counts[j] == 0:
                        spatial_names[row_index] = (
                            "OUTSIDE_BOUNDARIES"
                        )
                        outside_boundary += 1

                    elif hit_counts[j] > 1:
                        spatial_names[row_index] = (
                            "AMBIGUOUS_BOUNDARY"
                        )
                        ambiguous_boundary += 1

                    else:
                        spatial_names[row_index] = (
                            assigned_names[j]
                        )

            for i, row in enumerate(rows):

                source_borough = normalize_borough(
                    row.get("borough")
                )

                spatial_borough = (
                    spatial_names[i]
                    or "NO_VALID_COORDINATES"
                )

                source_counts[source_borough or "EMPTY"] += 1
                spatial_counts[spatial_borough] += 1

                if source_borough in BOROUGHS:

                    if spatial_borough in BOROUGHS:
                        compared += 1

                        if source_borough == spatial_borough:
                            matches += 1
                        else:
                            mismatches += 1

                            pair = (
                                f"{source_borough} -> "
                                f"{spatial_borough}"
                            )

                            mismatch_pairs[pair] += 1

                            writer.writerow({
                                "unique_key": row["unique_key"],
                                "created_date": row["created_date"],
                                "incident_zip": row["incident_zip"],
                                "source_borough": source_borough,
                                "spatial_borough": spatial_borough,
                                "latitude": row["latitude"],
                                "longitude": row["longitude"],
                                "discrepancy_type": "BOROUGH_MISMATCH",
                            })

                    elif spatial_borough in {
                        "OUTSIDE_BOUNDARIES",
                        "AMBIGUOUS_BOUNDARY",
                    }:
                        compared += 1
                        mismatches += 1

                        mismatch_pairs[
                            f"{source_borough} -> {spatial_borough}"
                        ] += 1

                        writer.writerow({
                            "unique_key": row["unique_key"],
                            "created_date": row["created_date"],
                            "incident_zip": row["incident_zip"],
                            "source_borough": source_borough,
                            "spatial_borough": spatial_borough,
                            "latitude": row["latitude"],
                            "longitude": row["longitude"],
                            "discrepancy_type": spatial_borough,
                        })

                elif source_borough in {"", "UNSPECIFIED"}:

                    unspecified += 1

                    if spatial_borough in BOROUGHS:
                        inferable_unspecified += 1
                        inferable_by_borough[
                            spatial_borough
                        ] += 1

                else:
                    invalid_source_borough += 1

    boundary_hash = hashlib.sha256(
        Path(boundary_path).read_bytes()
    ).hexdigest()

    report = {
        "total_records": total,
        "valid_coordinate_pairs": valid_coordinates,
        "missing_coordinate_pairs": missing_coordinates,
        "partial_coordinate_pairs": partial_coordinates,
        "invalid_coordinate_pairs": invalid_coordinates,
        "outside_boundary_records": outside_boundary,
        "ambiguous_boundary_records": ambiguous_boundary,
        "compared_records": compared,
        "matching_records": matches,
        "mismatching_records": mismatches,
        "match_rate_percent": round(
            matches / compared * 100, 4
        ) if compared else None,
        "unspecified_source_borough": unspecified,
        "unspecified_with_inferable_location": inferable_unspecified,
        "inferable_unspecified_by_borough": dict(
            inferable_by_borough
        ),
        "invalid_source_borough": invalid_source_borough,
        "source_borough_distribution": dict(source_counts),
        "spatial_borough_distribution": dict(spatial_counts),
        "mismatches_by_pair": dict(mismatch_pairs),
        "boundary_source": BOUNDARY_URL,
        "boundary_sha256": boundary_hash,
        "boundary_retrieved_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "comparison_method": "Point in polygon using incident latitude and longitude.",
    }

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return report
