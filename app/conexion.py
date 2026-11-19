
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine

# Cargar variables desde app/.env sin depender del directorio desde donde se inicia Uvicorn.
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))


class Conexion:
    """
    Gestiona la conexión a SQL Server mediante un único Engine
    compartido por toda la aplicación.

    Cada operación obtiene su propia conexión del pool.
    """

    _engine: Engine | None = None

    @classmethod
    def _url(cls) -> URL:
        servidor = os.getenv("DB_SERVER")
        base = os.getenv("DB_DATABASE")

        if not servidor or not base:
            raise RuntimeError(
                "Faltan DB_SERVER o DB_DATABASE en el archivo .env"
            )

        usuario = os.getenv("DB_USER")
        clave = os.getenv("DB_PASSWORD")

        query = {
            "driver": os.getenv(
                "DB_DRIVER",
                "ODBC Driver 18 for SQL Server"
            ),
            "TrustServerCertificate": "yes",
        }

        # Autenticación de SQL Server
        if usuario and clave:
            return URL.create(
                "mssql+pyodbc",
                username=usuario,
                password=clave,
                host=servidor,
                database=base,
                query=query,
            )

        # Autenticación de Windows
        query["Trusted_Connection"] = "yes"

        return URL.create(
            "mssql+pyodbc",
            host=servidor,
            database=base,
            query=query,
        )

    @classmethod
    def engine(cls) -> Engine:
        """
        Crea el Engine una sola vez.
        SQLAlchemy administra el pool de conexiones.
        """
        if cls._engine is None:
            cls._engine = create_engine(
                cls._url(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                pool_recycle=1800,
            )

        return cls._engine

    @classmethod
    @contextmanager
    def transaccion(cls) -> Iterator[Connection]:
        """
        Abre una transacción.

        Si todo sale bien: COMMIT.
        Si ocurre una excepción: ROLLBACK.
        """
        with cls.engine().begin() as connection:
            yield connection

    @classmethod
    def consultar(
        cls,
        sql: str,
        params: dict[str, Any] | None = None
    ) -> list[dict]:
        """Ejecuta consultas SELECT y devuelve una lista de diccionarios."""
        with cls.engine().connect() as connection:
            resultado = connection.execute(
                text(sql),
                params or {}
            )

            return [
                dict(fila._mapping)
                for fila in resultado
            ]

    @classmethod
    def ejecutar(
        cls,
        sql: str,
        params: dict[str, Any] | None = None
    ) -> int:
        """Ejecuta INSERT, UPDATE o DELETE con transacción automática."""
        with cls.transaccion() as connection:
            resultado = connection.execute(
                text(sql),
                params or {}
            )

            return resultado.rowcount

    @classmethod
    def fecha_servidor(cls):
        """Obtiene la fecha y hora del servidor SQL Server."""
        resultado = cls.consultar(
            "SELECT GETDATE() AS ahora"
        )

        return resultado[0]["ahora"]

    @classmethod
    def probar(cls) -> dict:
        """Comprueba la conexión y devuelve información del servidor."""
        resultado = cls.consultar("""
            SELECT
                DB_NAME() AS base,
                @@SERVERNAME AS servidor,
                GETDATE() AS ahora
        """)

        return resultado[0]

    @classmethod
    def cerrar(cls) -> None:
        """Cierra el pool de conexiones y permite recrearlo."""
        if cls._engine is not None:
            cls._engine.dispose()
            cls._engine = None
