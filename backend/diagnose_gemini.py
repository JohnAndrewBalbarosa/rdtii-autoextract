"""Diagnostic script to check available Gemini models for your API key."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import os

from dotenv import load_dotenv
load_dotenv()

def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set in your environment or .env file.")
        return

    print(f"Testing API key (starts with {api_key[:6]}...):")
    
    # 1. Test ListModels endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    print(f"Requesting: {url}")
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            models = res.get("models", [])
            print(f"\n[SUCCESS] Retrieved {len(models)} models:")
            for m in models:
                name = m.get("name", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    print(f"  - {name} ({m.get('displayName', '')})")
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        print(f"\n[HTTP ERROR] {e.code} {e.reason}")
        print(err_content)
    except Exception as e:
        print(f"\n[ERROR] Failed to query endpoint: {e}")

if __name__ == "__main__":
    main()
