"""Isolate the HuggingFace 403: bypasses fastembed/uvicorn entirely and
calls huggingface_hub directly, printing the full error if it fails.

Run from backend/ with the venv active:   py test_hf.py
"""
import os

from app.config import get_settings

s = get_settings()
print(f"HF_TOKEN loaded from .env: {bool(s.hf_token)} (len={len(s.hf_token)})")

if s.hf_token:
    os.environ["HF_TOKEN"] = s.hf_token

from huggingface_hub import model_info  # noqa: E402  (import after env is set)

try:
    info = model_info("qdrant/bge-small-en-v1.5-onnx-q", token=s.hf_token or None)
    print(f"SUCCESS: sha={info.sha}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    # Print raw response body if available — shows whether this is really
    # HuggingFace responding, or a corporate proxy block page.
    resp = getattr(e, "response", None)
    if resp is not None:
        print("--- response headers ---")
        print(dict(resp.headers))
        print("--- response body (first 500 chars) ---")
        print(resp.text[:500])
