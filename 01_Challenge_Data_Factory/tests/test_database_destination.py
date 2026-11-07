import pytest

from datetime import datetime
from sqlalchemy import DateTime

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    MetaData,
    Table,
    select,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError
from pandas.errors import DatabaseError as PandasDatabaseError

from data_factory.database_destination import DatabaseDestination


@pytest.fixture
def destination():
    db = DatabaseDestination("sqlite://")

    yield db

    db.close()


@pytest.fixture
def sql_types():
    return {
        "id": Integer(),
        "name": String(50),
    }


def test_write_csv_streams_all_records(
    destination,
    sql_types,
    tmp_path,
):
    csv_file = tmp_path / "records.csv"

    csv_file.write_text(
        "id,name\n"
        "1,Ali\n"
        "2,Sara\n"
        "3,John\n"
        "4,Mina\n"
        "5,Reza\n",
        encoding="utf-8",
    )

    written = destination.write_csv(
        file_path=csv_file,
        table_name="records",
        schema=None,
        dtype=sql_types,
        read_chunksize=2,
        write_chunksize=1,
    )

    assert written == 5

    with destination.engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM records")
        ).scalar_one()

    assert count == 5


def test_write_csv_rejects_missing_sql_types(
    destination,
    tmp_path,
):
    csv_file = tmp_path / "records.csv"

    csv_file.write_text(
        "id,name\n1,Ali\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Missing SQL data types",
    ):
        destination.write_csv(
            file_path=csv_file,
            table_name="records",
            schema=None,
            dtype={"id": Integer()},
        )



def test_write_csv_rolls_back_failed_transaction(
    destination,
    sql_types,
    tmp_path,
):
    csv_file = tmp_path / "records.csv"

    csv_file.write_text(
        "id,name\n"
        "1,Ali\n"
        "2,\n",
        encoding="utf-8",
    )

    with destination.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE records "
                "(id INTEGER NOT NULL, name VARCHAR(50) NOT NULL)"
            )
        )

    with pytest.raises(PandasDatabaseError) as exc_info:
        destination.write_csv(
            file_path=csv_file,
            table_name="records",
            schema=None,
            dtype=sql_types,
            read_chunksize=1,
            write_chunksize=1,
        )

    # Verify that Pandas wrapped the SQLAlchemy error.
    assert isinstance(
        exc_info.value.__cause__,
        IntegrityError,
    )

    # Verify that the failed transaction was rolled back.
    with destination.engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM records")
        ).scalar_one()

    assert count == 0



def test_write_csv_handles_header_only_file(
    destination,
    sql_types,
    tmp_path,
):
    csv_file = tmp_path / "empty.csv"

    csv_file.write_text(
        "id,name\n",
        encoding="utf-8",
    )

    written = destination.write_csv(
        file_path=csv_file,
        table_name="records",
        schema=None,
        dtype=sql_types,
    )

    assert written == 0

    assert not inspect(destination.engine).has_table(
        "records"
    )


def test_write_csv_rejects_invalid_chunk_size(
    destination,
    sql_types,
    tmp_path,
):
    csv_file = tmp_path / "records.csv"

    csv_file.write_text(
        "id,name\n1,Ali\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        destination.write_csv(
            file_path=csv_file,
            table_name="records",
            schema=None,
            dtype=sql_types,
            read_chunksize=0,
        )


def test_write_csv_rejects_missing_file(
    destination,
    sql_types,
    tmp_path,
):
    with pytest.raises(FileNotFoundError):
        destination.write_csv(
            file_path=tmp_path / "missing.csv",
            table_name="records",
            schema=None,
            dtype=sql_types,
        )


def test_write_csv_preserves_identifiers_and_parses_dates(
    destination,
    tmp_path,
):
    csv_file = tmp_path / "records.csv"

    csv_file.write_text(
        "unique_key,incident_zip,bbl,created_date\n"
        "00123,00501,0001234567,2024-01-01T00:00:20\n",
        encoding="utf-8",
    )

    sql_types = {
        "unique_key": String(20),
        "incident_zip": String(10),
        "bbl": String(20),
        "created_date": DateTime(),
    }

    written = destination.write_csv(
        file_path=csv_file,
        table_name="records",
        schema=None,
        dtype=sql_types,
        csv_dtype={
            "unique_key": "string",
            "incident_zip": "string",
            "bbl": "string",
        },
        parse_dates=[
            "created_date",
        ],
    )

    assert written == 1

    metadata = MetaData()

    records = Table(
        "records",
        metadata,
        autoload_with=destination.engine,
    )

    with destination.engine.connect() as conn:
        row = conn.execute(
            select(
                records.c.unique_key,
                records.c.incident_zip,
                records.c.bbl,
                records.c.created_date,
            )
        ).one()

    assert row.unique_key == "00123"
    assert row.incident_zip == "00501"
    assert row.bbl == "0001234567"
    assert row.created_date == datetime(2024, 1, 1, 0, 0, 20)
