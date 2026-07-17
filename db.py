"""
Oracle connection layer (oracledb, thin mode — no Oracle Client install needed).

Three databases, creds from .env:
  gasmarket()   VENCORP, STTM, WEATHERZONE, SEAGAS   (gas market)
  memarket()    TESTER, GSH                          (electricity market)
  gastrading()  tolling, gastrading                  (gas trading)

Use as context managers so connections always close:
    with db.gasmarket() as conn:
        df = pd.read_sql("SELECT ...", conn)
"""
from __future__ import annotations
import os
import oracledb

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env in project root
except ImportError:
    pass  # rely on real environment variables if python-dotenv absent


def _connect(prefix: str):
    """prefix in {'GASMARKET','MEMARKET','GASTRADING'} -> a live thin-mode connection."""
    return oracledb.connect(
        user=os.environ[f"{prefix}_USER"],
        password=os.environ[f"{prefix}_PASS"],
        dsn=os.environ[f"{prefix}_DSN"],
    )


def gasmarket():
    return _connect("GASMARKET")


def memarket():
    return _connect("MEMARKET")


def gastrading():
    return _connect("GASTRADING")
