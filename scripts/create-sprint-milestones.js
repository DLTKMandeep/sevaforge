#!/usr/bin/env node
/**
 * SevaForge SDLC — Create Sprint Milestones & Assign Issues
 *
 * Usage:
 *   GITHUB_TOKEN=ghp_xxx node create-sprint-milestones.js
 *
 *   Or if GITHUB_PERSONAL_ACCESS_TOKEN is already set (from your Claude Desktop config):
 *   node create-sprint-milestones.js
 */

const OWNER = 'DLTKMandeep';
const REPO = 'sevaforge';
const TOKEN = process.env.GITHUB_TOKEN || process.env.GITHUB_PERSONAL_ACCESS_TOKEN;

if (!TOKEN) {
  console.error('❌ Set GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN environment variable');
  process.exit(1);
}

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Accept': 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  'Content-Type': 'application/json'
};

async function api(method, path, body) {
  const url = `https://api.github.com/repos/${OWNER}/${REPO}${path}`;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok && res.status !== 422) {
    throw new Error(`${method} ${path} → ${res.status}: ${JSON.stringify(data)}`);
  }
  return { status: res.status, data };
}

async function createMilestone(title, description, due_on) {
  const { status, data } = await api('POST', '/milestones', { title, description, due_on });
  if (status === 422) {
    // Already exists — find it
    const { data: list } = await api('GET', '/milestones?state=open&per_page=100');
    const found = list.find(m => m.title === title);
    if (found) {
      console.log(`  ✅ Milestone already exists: "${title}" (#${found.number})`);
      return found.number;
    }
    throw new Error(`Milestone "${title}" creation failed and not found`);
  }
  console.log(`  ✅ Created milestone: "${title}" (#${data.number})`);
  return data.number;
}

async function main() {
  console.log('\n🚀 SevaForge Sprint Milestone Creator\n');
  console.log('Step 1: Creating milestones...\n');

  const sprintMap = {};

  sprintMap['sprint-2'] = await createMilestone(
    'Sprint 2 — Wire Smart Path + First 5 LLM Agents',
    'CLI --ai flag, execute_smart() wiring, confidence scoring, ModelRouter init, 5 agent LLM implementations.\nEpics: E1 (CLI AI Activation), E2 (Smart Execution Path), E3 (LLM-Augmented Agents)',
    '2026-07-10T07:00:00Z'
  );

  sprintMap['sprint-3'] = await createMilestone(
    'Sprint 3 — Data Layer & Persistence',
    'File ingestion pipeline, Git repo ingestion, ChromaDB persistent vector store, sentence-transformers embeddings, RAG CLI commands.\nEpics: E4 (Data Ingestion Pipeline), E5 (Persistent Vector Store)',
    '2026-07-24T07:00:00Z'
  );

  sprintMap['sprint-4'] = await createMilestone(
    'Sprint 4 — Feedback, Cost & Scale',
    'Feedback capture + auto-scoring, confidence calibration, cost tracking + budgets, cost-aware routing, 6+ LLM agent conversions, prompt library, E2E integration test.\nEpics: E6 (Feedback Loop), E7 (Cost Governance), E8 (Remaining LLM Agents)',
    '2026-08-07T07:00:00Z'
  );

  console.log(`\nMilestone IDs: sprint-2=#${sprintMap['sprint-2']}, sprint-3=#${sprintMap['sprint-3']}, sprint-4=#${sprintMap['sprint-4']}`);

  console.log('\nStep 2: Fetching all open issues...\n');

  let allIssues = [];
  let page = 1;
  while (true) {
    const { data } = await api('GET', `/issues?state=open&per_page=100&page=${page}`);
    if (data.length === 0) break;
    allIssues = allIssues.concat(data.filter(i => !i.pull_request));
    page++;
  }

  console.log(`  Found ${allIssues.length} open issues\n`);

  console.log('Step 3: Assigning issues to milestones...\n');

  let assigned = 0;
  for (const issue of allIssues) {
    const labels = issue.labels.map(l => l.name);
    let milestoneNum = null;

    if (labels.includes('sprint-2')) milestoneNum = sprintMap['sprint-2'];
    else if (labels.includes('sprint-3')) milestoneNum = sprintMap['sprint-3'];
    else if (labels.includes('sprint-4')) milestoneNum = sprintMap['sprint-4'];

    if (milestoneNum && (!issue.milestone || issue.milestone.number !== milestoneNum)) {
      await api('PATCH', `/issues/${issue.number}`, { milestone: milestoneNum });
      assigned++;
      const sprintLabel = labels.find(l => l.startsWith('sprint-'));
      console.log(`  ✅ #${issue.number} ${issue.title} → ${sprintLabel}`);
    }
  }

  console.log(`\n🎉 Done! Assigned ${assigned} issues to milestones.`);
  console.log(`\nView your sprint board: https://github.com/${OWNER}/${REPO}/milestones\n`);
}

main().catch(err => {
  console.error('❌ Error:', err.message);
  process.exit(1);
});
