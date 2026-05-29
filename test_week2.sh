#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# SevaForge Week 2 — Full API Test Script
# Start the server first: cd src && uvicorn sevaforge.api.app:create_app --factory --reload
# Then run: bash test_week2.sh
# ═══════════════════════════════════════════════════════════════

BASE="http://localhost:8000/api/v1"

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  1. AGENT-TO-AGENT MESSAGING"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Register Scanner Agent"
curl -s -X POST $BASE/a2a/agents \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"scanner","name":"Scanner Agent","capabilities":["scan","classify"]}' | python3 -m json.tool

echo ""
echo "→ Register Reviewer Agent"
curl -s -X POST $BASE/a2a/agents \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"reviewer","name":"Review Agent","capabilities":["review","approve"]}' | python3 -m json.tool

echo ""
echo "→ Register Deployer Agent"
curl -s -X POST $BASE/a2a/agents \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"deployer","name":"Deploy Agent","capabilities":["deploy","rollback"]}' | python3 -m json.tool

echo ""
echo "→ List all agents"
curl -s $BASE/a2a/agents | python3 -m json.tool

echo ""
echo "→ Send message: scanner → reviewer"
curl -s -X POST $BASE/a2a/send \
  -H "Content-Type: application/json" \
  -d '{"source":"scanner","target":"reviewer","payload":{"action":"review_code","file":"app.py","severity":"high"}}' | python3 -m json.tool

echo ""
echo "→ Send message: reviewer → deployer"
curl -s -X POST $BASE/a2a/send \
  -H "Content-Type: application/json" \
  -d '{"source":"reviewer","target":"deployer","payload":{"action":"deploy","version":"2.1.0","approved":true}}' | python3 -m json.tool

echo ""
echo "→ A2A Stats"
curl -s $BASE/a2a/stats | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  2. WORKFLOW ENGINE"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Create CI pipeline: scan → review → deploy"
WF_RESPONSE=$(curl -s -X POST $BASE/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name":"ci-pipeline",
    "nodes":[
      {"node_id":"scan","agent_id":"scanner"},
      {"node_id":"review","agent_id":"reviewer"},
      {"node_id":"deploy","agent_id":"deployer"}
    ],
    "edges":[
      {"source":"scan","target":"review"},
      {"source":"review","target":"deploy"}
    ]
  }')
echo $WF_RESPONSE | python3 -m json.tool
WF_ID=$(echo $WF_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['workflow_id'])")

echo ""
echo "→ Execute workflow: $WF_ID"
curl -s -X POST $BASE/workflows/$WF_ID/execute | python3 -m json.tool

echo ""
echo "→ List all workflows"
curl -s $BASE/workflows | python3 -m json.tool

echo ""
echo "→ Try cyclic workflow (should fail with 400)"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST $BASE/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name":"bad-cycle",
    "nodes":[{"node_id":"a","agent_id":"x"},{"node_id":"b","agent_id":"y"}],
    "edges":[{"source":"a","target":"b"},{"source":"b","target":"a"}]
  }' | head -20

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  3. CONTEXT MEMORY"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Create session"
SESSION_RESPONSE=$(curl -s -X POST $BASE/context/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id":"mandeep","tenant_id":"deltek"}')
echo $SESSION_RESPONSE | python3 -m json.tool
SID=$(echo $SESSION_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

echo ""
echo "→ Store state: scan_result"
curl -s -X POST $BASE/context/sessions/$SID/state \
  -H "Content-Type: application/json" \
  -d '{"key":"scan_result","value":{"score":0.95,"issues":3,"critical":1}}' | python3 -m json.tool

echo ""
echo "→ Store state: deployment_config"
curl -s -X POST $BASE/context/sessions/$SID/state \
  -H "Content-Type: application/json" \
  -d '{"key":"deployment_config","value":{"target":"gcp","region":"us-central1","replicas":3}}' | python3 -m json.tool

echo ""
echo "→ Add conversation turn (user)"
curl -s -X POST $BASE/context/sessions/$SID/turns \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"Scan the sevaforge repo for security vulnerabilities"}' | python3 -m json.tool

echo ""
echo "→ Add conversation turn (assistant)"
curl -s -X POST $BASE/context/sessions/$SID/turns \
  -H "Content-Type: application/json" \
  -d '{"role":"assistant","content":"Found 3 issues: 1 critical SQL injection in query builder, 2 medium severity XSS in templates"}' | python3 -m json.tool

echo ""
echo "→ Get full context window"
curl -s $BASE/context/sessions/$SID/window | python3 -m json.tool

echo ""
echo "→ Get conversation history"
curl -s $BASE/context/sessions/$SID/history | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  4. HYBRID SEARCH (Knowledge Layer)"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Index document: Terraform Guide"
curl -s -X POST $BASE/search/index \
  -H "Content-Type: application/json" \
  -d '{"title":"Terraform Guide","content":"Terraform is an infrastructure as code tool by HashiCorp for provisioning cloud resources on AWS GCP and Azure","collection":"devops"}' | python3 -m json.tool

echo ""
echo "→ Index document: Kubernetes Basics"
curl -s -X POST $BASE/search/index \
  -H "Content-Type: application/json" \
  -d '{"title":"Kubernetes Basics","content":"Kubernetes orchestrates containerized applications across clusters of machines with auto-scaling and self-healing","collection":"devops"}' | python3 -m json.tool

echo ""
echo "→ Index document: Python FastAPI"
curl -s -X POST $BASE/search/index \
  -H "Content-Type: application/json" \
  -d '{"title":"FastAPI Framework","content":"FastAPI is a modern Python web framework for building APIs with automatic OpenAPI documentation and type validation","collection":"backend"}' | python3 -m json.tool

echo ""
echo "→ Search: infrastructure as code (BM25)"
curl -s -X POST $BASE/search/query \
  -H "Content-Type: application/json" \
  -d '{"query":"infrastructure as code cloud","mode":"bm25"}' | python3 -m json.tool

echo ""
echo "→ Search: container orchestration (keyword)"
curl -s -X POST $BASE/search/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Kubernetes","mode":"keyword"}' | python3 -m json.tool

echo ""
echo "→ List collections"
curl -s $BASE/search/collections | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  5. KNOWLEDGE GRAPH"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Add entity: AIGateway (service)"
E1_RESPONSE=$(curl -s -X POST $BASE/graph/entities \
  -H "Content-Type: application/json" \
  -d '{"name":"AIGateway","entity_type":"service"}')
echo $E1_RESPONSE | python3 -m json.tool
EID1=$(echo $E1_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['entity_id'])")

echo ""
echo "→ Add entity: PostgreSQL (database)"
E2_RESPONSE=$(curl -s -X POST $BASE/graph/entities \
  -H "Content-Type: application/json" \
  -d '{"name":"PostgreSQL","entity_type":"database"}')
echo $E2_RESPONSE | python3 -m json.tool
EID2=$(echo $E2_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['entity_id'])")

echo ""
echo "→ Add entity: SemanticCache (service)"
E3_RESPONSE=$(curl -s -X POST $BASE/graph/entities \
  -H "Content-Type: application/json" \
  -d '{"name":"SemanticCache","entity_type":"service"}')
echo $E3_RESPONSE | python3 -m json.tool
EID3=$(echo $E3_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['entity_id'])")

echo ""
echo "→ Add relationship: AIGateway depends_on PostgreSQL"
curl -s -X POST $BASE/graph/relationships \
  -H "Content-Type: application/json" \
  -d "{\"source_id\":\"$EID1\",\"target_id\":\"$EID2\",\"relationship_type\":\"depends_on\"}" | python3 -m json.tool

echo ""
echo "→ Add relationship: AIGateway depends_on SemanticCache"
curl -s -X POST $BASE/graph/relationships \
  -H "Content-Type: application/json" \
  -d "{\"source_id\":\"$EID1\",\"target_id\":\"$EID3\",\"relationship_type\":\"depends_on\"}" | python3 -m json.tool

echo ""
echo "→ Get neighbors of AIGateway (depth=2)"
curl -s $BASE/graph/entities/$EID1/neighbors?depth=2 | python3 -m json.tool

echo ""
echo "→ Auto-extract entities from text"
curl -s -X POST $BASE/graph/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"The PromptEngine uses PostgreSQL and Redis for the SemanticCache and AIGateway"}' | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  6. RERANKER"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Rerank search results"
curl -s -X POST $BASE/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "query":"Python web development",
    "candidates":[
      {"doc_id":"d1","content":"Python Django web framework for rapid development","title":"Django","score":0.8,"rank":1},
      {"doc_id":"d2","content":"Cooking Italian pasta dishes and recipes","title":"Pasta Recipes","score":0.7,"rank":2},
      {"doc_id":"d3","content":"Python FastAPI modern async web framework","title":"FastAPI","score":0.6,"rank":3}
    ],
    "top_k":5
  }' | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  7. DATA LAYER — PostgreSQL"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Database health check"
curl -s $BASE/db/health | python3 -m json.tool

echo ""
echo "→ Insert record into users table"
INSERT_RESPONSE=$(curl -s -X POST $BASE/db/users/records \
  -H "Content-Type: application/json" \
  -d '{"data":{"name":"Mandeep Singh","role":"architect","team":"platform","email":"mandeepsingh@deltek.com"}}')
echo $INSERT_RESPONSE | python3 -m json.tool
RID=$(echo $INSERT_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo ""
echo "→ Get record"
curl -s $BASE/db/users/records/$RID | python3 -m json.tool

echo ""
echo "→ Update record"
curl -s -X PUT $BASE/db/users/records/$RID \
  -H "Content-Type: application/json" \
  -d '{"updates":{"role":"lead architect","team":"sevaforge"}}' | python3 -m json.tool

echo ""
echo "→ Get updated record"
curl -s $BASE/db/users/records/$RID | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  8. DATA LAYER — Redis"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Set session data"
curl -s -X POST $BASE/redis/sessions/set \
  -H "Content-Type: application/json" \
  -d '{"key":"session-mandeep","field_name":"last_action","value":"deployed v2.1.0"}' | python3 -m json.tool

echo ""
echo "→ Set more session data"
curl -s -X POST $BASE/redis/sessions/set \
  -H "Content-Type: application/json" \
  -d '{"key":"session-mandeep","field_name":"environment","value":"production"}' | python3 -m json.tool

echo ""
echo "→ Get session"
curl -s $BASE/redis/sessions/session-mandeep | python3 -m json.tool

echo ""
echo "→ Rate limit check (should be allowed)"
curl -s -X POST $BASE/redis/rate-limit/check \
  -H "Content-Type: application/json" \
  -d '{"key":"api-mandeep","cost":1}' | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  9. DATA LAYER — Event Stream"
echo "══════════════════════════════════════════════════════════"

echo ""
echo "→ Emit event: workflow completed"
curl -s -X POST $BASE/events/emit \
  -H "Content-Type: application/json" \
  -d '{"event_type":"workflow.completed","source":"ci-pipeline","data":{"duration_ms":1250,"status":"success","nodes_executed":3}}' | python3 -m json.tool

echo ""
echo "→ Emit event: agent registered"
curl -s -X POST $BASE/events/emit \
  -H "Content-Type: application/json" \
  -d '{"event_type":"agent.registered","source":"system","data":{"agent_id":"scanner","capabilities":["scan"]}}' | python3 -m json.tool

echo ""
echo "→ Emit event: cache hit"
curl -s -X POST $BASE/events/emit \
  -H "Content-Type: application/json" \
  -d '{"event_type":"cache.hit","source":"semantic-cache","data":{"prompt_hash":"abc123","savings_ms":450}}' | python3 -m json.tool

echo ""
echo "→ Event history"
curl -s "$BASE/events/history?source=ci-pipeline" | python3 -m json.tool

echo ""
echo "→ Event stats"
curl -s $BASE/events/stats | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  ALL WEEK 2 TESTS COMPLETE"
echo "══════════════════════════════════════════════════════════"
echo ""
