# modules/gcs.py

import os
import config
from google.cloud import storage
from dotenv import load_dotenv
from io import BytesIO
from xhtml2pdf import pisa


load_dotenv()
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = storage.Client()
    return _client

def _get_bucket():
    return _get_client().bucket(config.GCS_BUCKET_NAME)

# =============== FLAG-CONTROLLED I/O ===============

def write_bytes(content: bytes, remote_path: str, is_local: bool, content_type: str = "application/octet-stream"):
    if is_local:
        os.makedirs(os.path.dirname(remote_path), exist_ok=True)
        with open(remote_path, "wb") as f:
            f.write(content)
    else:
        # Normalize key for GCS (in case Windows backslashes exist)
        remote_path = remote_path.replace("\\", "/")
        blob = _get_bucket().blob(remote_path)
        blob.upload_from_string(content, content_type=content_type)
        print(f"⬆️ Uploaded to GCS: {remote_path} ({content_type})")



def read_bytes(remote_path: str, is_local: bool) -> bytes:
    """Read bytes from local or GCS based on flag."""
    if is_local:
        with open(remote_path, "rb") as f:
            return f.read()
    else:
        blob = _get_bucket().blob(remote_path)
        if not blob.exists():
            raise FileNotFoundError(f"[GCS] File not found: {remote_path}")
        return blob.download_as_bytes()

def save_dataframe(df, path: str, is_local: bool):
    """Save Pandas dataframe as CSV to local or GCS."""
    if is_local:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path, index=False)
    else:
        buf = BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)
        write_bytes(buf.read(), path, is_local)

def load_dataframe(path: str, is_local: bool):
    """Load Pandas dataframe from local or GCS."""
    import pandas as pd
    if is_local:
        return pd.read_csv(path)
    else:
        content = read_bytes(path, is_local)
        return pd.read_csv(BytesIO(content))

def smart_savefig(fig, path: str, is_local: bool, **kwargs):
    """Save matplotlib figure locally or to GCS directly."""
    if is_local:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fig.savefig(path, **kwargs)
    else:
        buf = BytesIO()
        fig.savefig(buf, format="png", **kwargs)
        buf.seek(0)
        write_bytes(buf.read(), path, is_local, content_type="image/png")


def save_pdf(html_content: str, path: str, is_local: bool):
    from xhtml2pdf import pisa
    from io import BytesIO

    output = BytesIO()
    pisa.CreatePDF(html_content, dest=output)
    output.seek(0)

    if is_local:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(output.read())
    else:
        from modules.gcs import write_bytes  # make sure this is included
        write_bytes(output.read(), path, is_local=False, content_type="application/pdf")
        print(f"✅ Saved PDF to GCS: {path}")  # ✅ for debug

def upload_blob_from_bytes(content: bytes, destination_blob_name: str, content_type="application/pdf"):
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(config.GCS_BUCKET_NAME)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_string(content, content_type=content_type)
    print(f"✅ Uploaded to GCS at: {destination_blob_name}")


