#!/bin/bash
# Generate KB API SDK from OpenAPI spec.
# Usage: bash scripts/generate_kb_sdk.sh [python|typescript]
set -euo pipefail

SDK_LANG="${1:-python}"
OPENAPI_URL="${AIPLAT_PLATFORM_URL:-http://localhost:8003}/openapi.json"
OUTPUT_DIR="${AIPLAT_HOME:-$HOME/.aiplat}/sdk/${SDK_LANG}"

echo "Fetching OpenAPI spec from ${OPENAPI_URL}..."
mkdir -p "$OUTPUT_DIR"

if command -v curl &>/dev/null; then
    curl -s "$OPENAPI_URL" -o /tmp/aiplat_kb_openapi.json
else
    python3 -c "import urllib.request,json;open('/tmp/aiplat_kb_openapi.json','w').write(json.dumps(json.load(urllib.request.urlopen('$OPENAPI_URL')),indent=2))"
fi

# Extract KB-relevant endpoints
python3 -c "
import json
with open('/tmp/aiplat_kb_openapi.json') as f:
    spec = json.load(f)
kb_paths = {p:m for p,m in spec.get('paths',{}).items() if '/kb/' in p or '/conversations' in p or '/documents' in p}
spec['paths'] = kb_paths
with open('/tmp/aiplat_kb_openapi.json', 'w') as f:
    json.dump(spec, f, indent=2)
print(f'Extracted {len(kb_paths)} KB endpoints')
"

if [ "$SDK_LANG" = "python" ]; then
    echo "Generating Python SDK..."
    if python3 -c "import openapi_codegen" 2>/dev/null; then
        python3 -m openapi_codegen /tmp/aiplat_kb_openapi.json "$OUTPUT_DIR" --package aiplat_kb_sdk
    else
        # Minimal SDK stub
        cat > "$OUTPUT_DIR/__init__.py" << 'PYEOF'
"""aiPlat KB SDK — auto-generated client for knowledge base API."""
import os, json, urllib.request
from typing import Any, Dict, List, Optional

class KBSdkClient:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv("AIPLAT_PLATFORM_URL", "http://localhost:8003")).rstrip("/")
    def _req(self, method: str, path: str, data: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    def list_documents(self, collection_id="default"): return self._req("GET", f"/platform/kb/collections/{collection_id}/documents")
    def upload_document(self, collection_id, file_path, kind): raise NotImplementedError("use multipart upload directly")
    def get_stats(self): return self._req("GET", "/platform/kb/stats")
    def reindex(self): return self._req("POST", "/platform/kb/reindex")
    def create_conversation(self, title, scope): return self._req("POST", "/platform/conversations", {"title":title,"scope":scope,"profile":{}})
    def query_conversation(self, session_id, message): return self._req("POST", f"/platform/conversations/{session_id}/query", {"message":message})
PYEOF
        echo "  Created minimal Python SDK: $OUTPUT_DIR/__init__.py"
    fi
elif [ "$SDK_LANG" = "typescript" ]; then
    echo "Generating TypeScript SDK..."
    cat > "$OUTPUT_DIR/index.ts" << 'TSEOF'
// aiPlat KB SDK — auto-generated TypeScript client
const BASE = import.meta.env.VITE_API_URL || '/api';
export interface KBDocument { doc_id: string; collection_id: string; kind: string; status: string; }
export interface KBStats { documents: number; elements: number; embeddings: number; }
export async function listDocuments(collectionId = 'default'): Promise<{documents:KBDocument[],total:number}> {
  const r = await fetch(`${BASE}/platform/kb/collections/${collectionId}/documents`);
  return r.json();
}
export async function getStats(): Promise<KBStats> {
  const r = await fetch(`${BASE}/platform/kb/stats`);
  return r.json();
}
export async function reindex(): Promise<{status:string,count:number}> {
  const r = await fetch(`${BASE}/platform/kb/reindex`, {method:'POST'});
  return r.json();
}
export async function createConversation(title: string, docIds: string[]) {
  const r = await fetch(`${BASE}/platform/conversations`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, scope:{collection_id:'default',doc_ids:docIds}, profile:{}})
  });
  return r.json();
}
export async function queryConversation(sessionId: string, message: string) {
  const r = await fetch(`${BASE}/platform/conversations/${sessionId}/query`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({message})
  });
  return r.json();
}
TSEOF
    echo "  Created TypeScript SDK: $OUTPUT_DIR/index.ts"
fi

echo "SDK generation complete: $OUTPUT_DIR"
