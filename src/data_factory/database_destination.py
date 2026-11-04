
from pathlib import Path

from sqlalchemy import create_engine


class DatabaseDestination:
    """
    Reusable SQLAlchemy destination for DataFrames and CSV files.
    """

    def __init__(self, database_url, **engine_options):
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
            **engine_options,
        )

    def transaction(self):
        return self.engine.begin()

    @staticmethod
    def _validate_dtype(columns, dtype):
        if not isinstance(dtype, dict):
            raise TypeError(
                "Explicit SQLAlchemy dtype mapping is required."
            )

        missing_types = set(columns) - set(dtype)

        if missing_types:
            raise ValueError(
                f"Missing SQL data types: {sorted(missing_types)}"
            )

    def write_dataframe(
        self,
        dataframe,
        table_name,
        schema,
        dtype,
        connection=None,
        chunksize=2000,
    ):
        if dataframe.empty:
            return 0

        self._validate_dtype(dataframe.columns, dtype)

        if connection is None:
            with self.engine.begin() as conn:
                return self.write_dataframe(
                    dataframe=dataframe,
                    table_name=table_name,
                    schema=schema,
                    dtype=dtype,
                    connection=conn,
                    chunksize=chunksize,
                )

        dataframe.to_sql(
            name=table_name,
            schema=schema,
            con=connection,
            if_exists="append",
            index=False,
            dtype=dtype,
            chunksize=chunksize,
        )

        return len(dataframe)

    def write_csv(
        self,
        file_path,
        table_name,
        schema,
        dtype,
        read_chunksize=20000,
        write_chunksize=2000,
        encoding="utf-8-sig",
        connection=None,
        csv_dtype=None,
        parse_dates=None,
    ):
        """
        Stream a CSV file into the database.

        When no connection is provided, all chunks are
        written inside one transaction.
        """

        import pandas as pd

        if (
            not isinstance(read_chunksize, int)
            or isinstance(read_chunksize, bool)
            or read_chunksize <= 0
        ):
            raise ValueError(
                "read_chunksize must be a positive integer."
            )

        if (
            not isinstance(write_chunksize, int)
            or isinstance(write_chunksize, bool)
            or write_chunksize <= 0
        ):
            raise ValueError(
                "write_chunksize must be a positive integer."
            )

        file_path = Path(file_path)

        if not file_path.is_file():
            raise FileNotFoundError(
                f"CSV file not found: {file_path}"
            )

        # Validate SQL types before writing any records.
        header = pd.read_csv(
            file_path,
            nrows=0,
            encoding=encoding,
        )

        self._validate_dtype(header.columns, dtype)

        def write_chunks(conn):
            total_rows = 0

            reader = pd.read_csv(
                file_path,
                chunksize=read_chunksize,
                encoding=encoding,
                dtype=csv_dtype,
                parse_dates=parse_dates,
            )

            for chunk in reader:
                written = self.write_dataframe(
                    dataframe=chunk,
                    table_name=table_name,
                    schema=schema,
                    dtype=dtype,
                    connection=conn,
                    chunksize=write_chunksize,
                )

                total_rows += written

            return total_rows

        if connection is not None:
            return write_chunks(connection)

        with self.engine.begin() as conn:
            return write_chunks(conn)

    def close(self):
        self.engine.dispose()
