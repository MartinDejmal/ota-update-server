import os, tempfile
os.environ["DATA_DIR"]=tempfile.mkdtemp()
from app.api import app
from app.db import init_db

def test_health():
    init_db()
    assert app.title == "OTA Update Server"
