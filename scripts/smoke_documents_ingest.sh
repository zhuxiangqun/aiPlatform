#!/usr/bin/env bash
set -euo pipefail

# 最小冒烟：启动服务 → ingest fixture → 轮询 job → 校验 elements 写入

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$ROOT_DIR/aiPlat-core/core/harness/smoke/fixtures/sample.pdf"

API_KEY="${AIPLAT_API_KEY:-apl_dev}"
TENANT_ID="${AIPLAT_TENANT_ID:-default}"

echo "[smoke] restart services..."
# Avoid MinerU stalls for smoke.
export AIPLAT_KB_PARSER="${AIPLAT_KB_PARSER:-ocr}"
export AIPLAT_ENABLE_MINERU_API="${AIPLAT_ENABLE_MINERU_API:-0}"
# Silence pip "script location" warnings during bootstrap; still show failures.
export PIP_NO_WARN_SCRIPT_LOCATION=1
set +e
BOOT_LOG="$(mktemp -t aiplat-smoke-boot.XXXXXX)"
"$ROOT_DIR/restart.sh" >"$BOOT_LOG" 2>&1
RC=$?
set -e
if [ $RC -ne 0 ]; then
  echo "[smoke] ERROR: restart failed (rc=$RC)"
  tail -n 120 "$BOOT_LOG" || true
  exit 10
fi

echo "[smoke] ingest fixture: $FIXTURE"
RESP="$(curl -s -X POST "http://localhost:8003/api/v1/documents/ingest" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -F "file=@${FIXTURE}" \
  -F "collection_id=default")"

JOB_ID="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("job_id") or ""))' <<<"$RESP")"
DOC_ID="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("doc_id") or ""))' <<<"$RESP")"

if [ -z "$JOB_ID" ] || [ -z "$DOC_ID" ]; then
  echo "[smoke] ingest response:"
  echo "$RESP"
  echo "[smoke] ERROR: missing job_id/doc_id"
  exit 1
fi

echo "[smoke] job_id=$JOB_ID doc_id=$DOC_ID"

echo "[smoke] polling job..."
for i in {1..60}; do
  J="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${JOB_ID}" \
    -H "X-AIPLAT-API-KEY: ${API_KEY}" \
    -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
  ST="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' <<<"$J")"
  MSG="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("message",""))' <<<"$J")"
  echo "  - $i status=$ST message=$MSG"
  if [ "$ST" = "completed" ]; then
    break
  fi
  if [ "$ST" = "failed" ]; then
    echo "[smoke] job failed:"
    echo "$J"
    exit 2
  fi
  sleep 1
done

echo "[smoke] verify kb_elements written (sqlite3 must be available)"
SQLITE_DB="$ROOT_DIR/.aiplat/kb/tenants/${TENANT_ID}/kb.sqlite3"
if [ ! -f "$SQLITE_DB" ]; then
  # fallback to home dir layout
  SQLITE_DB="$HOME/.aiplat/kb/tenants/${TENANT_ID}/kb.sqlite3"
fi

COUNT="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_elements where doc_id='${DOC_ID}';")"
echo "[smoke] kb_elements count = $COUNT"
if [ "${COUNT}" -le 0 ]; then
  echo "[smoke] ERROR: kb_elements not written"
  exit 3
fi

EMB_COUNT="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_embeddings where doc_id='${DOC_ID}';")"
echo "[smoke] kb_embeddings count = $EMB_COUNT"
if [ "${EMB_COUNT}" -le 0 ]; then
  echo "[smoke] ERROR: kb_embeddings not written"
  exit 3
fi

echo "[smoke] verify platform elements api returns items"
ELS="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}/elements?limit=5" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
ELS_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("items") or []))' <<<"$ELS")"
echo "[smoke] elements api items = $ELS_N"
if [ "${ELS_N}" -le 0 ]; then
  echo "[smoke] ERROR: elements api returned no items"
  echo "$ELS"
  exit 4
fi

echo "[smoke] verify documents list/detail/sources api works"
DL="$(curl -s "http://localhost:8003/api/v1/documents?collection_id=default&limit=5" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
DL_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("items") or []))' <<<"$DL")"
if [ "${DL_N}" -le 0 ]; then
  echo "[smoke] ERROR: documents list returned no items"
  echo "$DL"
  exit 4
fi
DD="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
DD_OK="$(python -c 'import json,sys; d=json.load(sys.stdin); print(1 if d.get("doc_id") else 0)' <<<"$DD")"
if [ "${DD_OK}" -le 0 ]; then
  echo "[smoke] ERROR: document detail missing doc_id"
  echo "$DD"
  exit 4
fi
DS="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}/sources?limit=5" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
DS_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("items") or []))' <<<"$DS")"
if [ "${DS_N}" -le 0 ]; then
  echo "[smoke] ERROR: document sources returned no items"
  echo "$DS"
  exit 4
fi

echo "[smoke] verify document export api works"
EXJ="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}/export?format=json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
EXJ_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("elements") or []))' <<<"$EXJ")"
if [ "${EXJ_N}" -le 0 ]; then
  echo "[smoke] ERROR: export json returned no elements"
  echo "$EXJ"
  exit 4
fi
EXM="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}/export?format=markdown" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
EXM_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len((d.get("content") or "").strip()))' <<<"$EXM")"
if [ "${EXM_N}" -le 0 ]; then
  echo "[smoke] ERROR: export markdown content is empty"
  echo "$EXM"
  exit 4
fi

echo "[smoke] verify doc query api works"
Q="$(curl -s "http://localhost:8003/api/v1/documents/query" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"doc_id\":\"${DOC_ID}\",\"collection_id\":\"default\",\"question\":\"Hello aiPlat 是什么？\",\"top_k\":3}")"
Q_N="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len(o.get("items") or []))' <<<"$Q")"
Q_A="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len((o.get("answer") or "").strip()))' <<<"$Q")"
Q_M="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len((o.get("mode") or "").strip()))' <<<"$Q")"
echo "[smoke] query items = $Q_N"
if [ "${Q_N}" -le 0 ]; then
  echo "[smoke] ERROR: query returned no items"
  echo "$Q"
  exit 5
fi
if [ "${Q_A}" -le 0 ]; then
  echo "[smoke] ERROR: query answer is empty"
  echo "$Q"
  exit 5
fi
if [ "${Q_M}" -le 0 ]; then
  echo "[smoke] ERROR: query mode is empty"
  echo "$Q"
  exit 5
fi

echo "[smoke] verify collection query api works"
CQ="$(curl -s "http://localhost:8003/api/v1/collections/query" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"collection_id\":\"default\",\"question\":\"Hello aiPlat\",\"top_k\":3}")"
CQ_N="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len(o.get("items") or []))' <<<"$CQ")"
echo "[smoke] collection query items = $CQ_N"
if [ "${CQ_N}" -le 0 ]; then
  echo "[smoke] ERROR: collection query returned no items"
  echo "$CQ"
  exit 7
fi

echo "[smoke] verify doc summarize api works"
S="$(curl -s "http://localhost:8003/api/v1/documents/summarize" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"doc_id\":\"${DOC_ID}\",\"profile\":\"key_points\",\"max_points\":3}")"
S_N="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len(o.get("points") or []))' <<<"$S")"
S_SUM="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len((o.get("summary") or "").strip()))' <<<"$S")"
S_M="$(python -c 'import json,sys; d=json.load(sys.stdin); o=d.get("output") or {}; print(len((o.get("mode") or "").strip()))' <<<"$S")"
echo "[smoke] summarize points = $S_N"
if [ "${S_N}" -le 0 ]; then
  echo "[smoke] ERROR: summarize returned no points"
  echo "$S"
  exit 6
fi
if [ "${S_SUM}" -le 0 ]; then
  echo "[smoke] ERROR: summarize summary is empty"
  echo "$S"
  exit 6
fi
if [ "${S_M}" -le 0 ]; then
  echo "[smoke] ERROR: summarize mode is empty"
  echo "$S"
  exit 6
fi

echo "[smoke] verify analysis runs api works"
AR="$(curl -s "http://localhost:8003/api/v1/documents/${DOC_ID}/analysis-runs?limit=10" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
AR_N="$(python -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("items") or []))' <<<"$AR")"
echo "[smoke] analysis runs = $AR_N"
if [ "${AR_N}" -le 0 ]; then
  echo "[smoke] ERROR: analysis runs returned no items"
  echo "$AR"
  exit 6
fi

echo "[smoke] verify url ingest works (file://)"
URL_JSON="$(python -c 'import json,sys; import pathlib; p=pathlib.Path(sys.argv[1]).resolve(); print(json.dumps({"collection_id":"default","url":"file://"+str(p), "kind":"pdf"}))' "$FIXTURE")"
RESP2="$(curl -s -X POST "http://localhost:8003/api/v1/documents/ingest" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "$URL_JSON")"
JOB_ID2="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("job_id") or ""))' <<<"$RESP2")"
DOC_ID2="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("doc_id") or ""))' <<<"$RESP2")"
if [ -z "$JOB_ID2" ] || [ -z "$DOC_ID2" ]; then
  echo "[smoke] url ingest response:"
  echo "$RESP2"
  echo "[smoke] ERROR: missing job_id/doc_id for url ingest"
  exit 11
fi
echo "[smoke] url ingest job_id=$JOB_ID2 doc_id=$DOC_ID2"
for i in {1..60}; do
  J="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${JOB_ID2}" \
    -H "X-AIPLAT-API-KEY: ${API_KEY}" \
    -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
  ST="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' <<<"$J")"
  if [ "$ST" = "completed" ]; then
    break
  fi
  if [ "$ST" = "failed" ]; then
    echo "[smoke] url ingest job failed:"
    echo "$J"
    exit 12
  fi
  sleep 1
done
COUNT2="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_elements where doc_id='${DOC_ID2}';")"
echo "[smoke] url ingest kb_elements count = $COUNT2"
if [ "${COUNT2}" -le 0 ]; then
  echo "[smoke] ERROR: url ingest kb_elements not written"
  exit 13
fi

echo "[smoke] verify url ingest works (http://127.0.0.1)"
PORT="${SMOKE_HTTP_PORT:-18080}"
HTTP_LOG="$(mktemp -t aiplat-smoke-http.XXXXXX)"
bash "$ROOT_DIR/scripts/smoke_http_server.sh" >"$HTTP_LOG" 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID >/dev/null 2>&1 || true' EXIT
sleep 1

URL_HTML="http://127.0.0.1:${PORT}/sample.html"
URL_PDF="http://127.0.0.1:${PORT}/sample.pdf"

RESP3="$(curl -s -X POST "http://localhost:8003/api/v1/documents/ingest" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"collection_id\":\"default\",\"url\":\"${URL_HTML}\",\"kind\":\"html\"}")"
JOB_ID3="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("job_id") or ""))' <<<"$RESP3")"
DOC_ID3="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("doc_id") or ""))' <<<"$RESP3")"
if [ -z "$JOB_ID3" ] || [ -z "$DOC_ID3" ]; then
  echo "[smoke] http html ingest response:"
  echo "$RESP3"
  exit 14
fi
for i in {1..60}; do
  J="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${JOB_ID3}" \
    -H "X-AIPLAT-API-KEY: ${API_KEY}" \
    -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
  ST="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' <<<"$J")"
  if [ "$ST" = "completed" ]; then
    break
  fi
  if [ "$ST" = "failed" ]; then
    echo "[smoke] http html ingest job failed:"
    echo "$J"
    exit 15
  fi
  sleep 1
done
COUNT3="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_elements where doc_id='${DOC_ID3}';")"
echo "[smoke] http html kb_elements count = $COUNT3"
if [ "${COUNT3}" -le 0 ]; then
  echo "[smoke] ERROR: http html kb_elements not written"
  exit 16
fi

echo "[smoke] verify url cache/dedupe works (second html ingest)"
RESP3B="$(curl -s -X POST "http://localhost:8003/api/v1/documents/ingest" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"collection_id\":\"default\",\"url\":\"${URL_HTML}\",\"kind\":\"html\"}")"
JOB_ID3B="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("job_id") or ""))' <<<"$RESP3B")"
if [ -z "$JOB_ID3B" ]; then
  echo "[smoke] second html ingest response:"
  echo "$RESP3B"
  exit 20
fi
J3B="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${JOB_ID3B}" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
MSG3B="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("message",""))' <<<"$J3B")"
echo "[smoke] second html ingest job message = $MSG3B"
if [ "$MSG3B" != "dedupe_hit" ]; then
  echo "[smoke] ERROR: second html ingest should be dedupe_hit"
  echo "$J3B"
  exit 21
fi
COUNT3B="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_elements where doc_id='${DOC_ID3}';")"
echo "[smoke] http html kb_elements count after dedupe = $COUNT3B"
if [ "${COUNT3B}" -ne "${COUNT3}" ]; then
  echo "[smoke] ERROR: html elements count changed after dedupe (before=${COUNT3}, after=${COUNT3B})"
  exit 22
fi

echo "[smoke] verify document refresh api works"
RF="$(curl -s -X POST "http://localhost:8003/api/v1/documents/${DOC_ID3}/refresh" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d '{"force":false}')"
RF_JOB="$(python -c 'import json,sys; d=json.load(sys.stdin); j=d.get("job") or {}; print((j.get("job_id") or ""))' <<<"$RF")"
if [ -z "$RF_JOB" ]; then
  echo "[smoke] ERROR: refresh missing job_id"
  echo "$RF"
  exit 23
fi
RFJ="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${RF_JOB}" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
RFM="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("message",""))' <<<"$RFJ")"
echo "[smoke] refresh job message = $RFM"
if [ -z "$RFM" ]; then
  echo "[smoke] ERROR: refresh job message empty"
  echo "$RFJ"
  exit 24
fi

RESP4="$(curl -s -X POST "http://localhost:8003/api/v1/documents/ingest" \
  -H "Content-Type: application/json" \
  -H "X-AIPLAT-API-KEY: ${API_KEY}" \
  -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}" \
  -d "{\"collection_id\":\"default\",\"url\":\"${URL_PDF}\",\"kind\":\"pdf\"}")"
JOB_ID4="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("job_id") or ""))' <<<"$RESP4")"
DOC_ID4="$(python -c 'import json,sys
d=json.load(sys.stdin)
j=d.get("job") or {}
if not j:
  j=(d.get("core") or {}).get("output") or {}
print((j.get("doc_id") or ""))' <<<"$RESP4")"
if [ -z "$JOB_ID4" ] || [ -z "$DOC_ID4" ]; then
  echo "[smoke] http pdf ingest response:"
  echo "$RESP4"
  exit 17
fi
for i in {1..60}; do
  J="$(curl -s "http://localhost:8003/api/v1/kb/jobs/${JOB_ID4}" \
    -H "X-AIPLAT-API-KEY: ${API_KEY}" \
    -H "X-AIPLAT-TENANT-ID: ${TENANT_ID}")"
  ST="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""))' <<<"$J")"
  if [ "$ST" = "completed" ]; then
    break
  fi
  if [ "$ST" = "failed" ]; then
    echo "[smoke] http pdf ingest job failed:"
    echo "$J"
    exit 18
  fi
  sleep 1
done
COUNT4="$(sqlite3 "$SQLITE_DB" "select count(*) from kb_elements where doc_id='${DOC_ID4}';")"
echo "[smoke] http pdf kb_elements count = $COUNT4"
if [ "${COUNT4}" -le 0 ]; then
  echo "[smoke] ERROR: http pdf kb_elements not written"
  exit 19
fi

echo "[smoke] OK"
