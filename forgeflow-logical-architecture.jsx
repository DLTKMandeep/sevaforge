import { useState } from "react";

const PHASES = [
  {
    id: "analyse",
    label: "Analyse",
    icon: "📊",
    color: "#8b5cf6",
    bgLight: "#ede9fe",
    desc: "Understand the repository",
    stages: [
      { id: "discover", label: "Discover", icon: "🔍", agent: "DiscoveryAgent", mcp: "discovery-mcp-server", input: "Repository path", output: ".forgeflow/inventory.json", desc: "Scans repo structure — languages, frameworks, entry points, Docker/K8s presence, CI/CD configs" },
      { id: "normalize", label: "Normalize", icon: "📐", agent: "NormalizationAgent", mcp: "normalize-mcp-server", input: "inventory.json", output: ".gitignore, pyproject.toml, .editorconfig", desc: "Adds missing standard files to meet baseline engineering standards" },
      { id: "docs", label: "Docs", icon: "📝", agent: "DocumentationAgent", mcp: "diagram-generator-mcp-server", input: "inventory.json", output: "docs/ARCHITECTURE.md, Mermaid diagrams", desc: "Generates architecture diagrams and documentation from discovered inventory" },
    ],
  },
  {
    id: "build",
    label: "Build",
    icon: "🔨",
    color: "#f59e0b",
    bgLight: "#fef3c7",
    desc: "Generate infrastructure & CI/CD",
    stages: [
      { id: "iac", label: "IaC", icon: "🏗️", agent: "IACAgent", mcp: "iac-mcp-server", input: "inventory.json", output: "infrastructure/{cloud}/*.tf, Dockerfile", desc: "Terraform for VPC, networking, IAM. Language-aware Dockerfile generation." },
      { id: "cd", label: "CD", icon: "🚀", agent: "CDAgent", mcp: "cd-mcp-server", input: "inventory.json", output: ".github/workflows/, K8s manifests, Kustomize", desc: "Complete GitOps delivery — workflows, Kustomize overlays, ArgoCD manifests" },
      { id: "ci", label: "CI", icon: "⚙️", agent: "CIAgent", mcp: "ci-mcp-server", input: "inventory.json", output: ".github/workflows/ci.yml, dependabot.yml", desc: "CI pipeline — build, lint, test, coverage, security scan, Dependabot" },
      { id: "e2e", label: "E2E", icon: "🧪", agent: "E2ETestingAgent", mcp: "e2e-mcp-server", input: "inventory.json", output: "tests/e2e/, playwright.config.ts", desc: "End-to-end test suite scaffolding — Playwright or Cypress" },
    ],
  },
  {
    id: "quality",
    label: "Quality",
    icon: "✅",
    color: "#10b981",
    bgLight: "#d1fae5",
    desc: "Validate code & security",
    stages: [
      { id: "review", label: "Review", icon: "👁️", agent: "CodeReviewAgent", mcp: "git-mcp-server", input: "Git history", output: "Quality findings", desc: "Git history analysis — commit frequency, PR size, code churn, tech debt" },
      { id: "test", label: "Test", icon: "🧪", agent: "TestingAgent", mcp: "cicd-mcp-server", input: "Test suite", output: "Coverage report", desc: "Runs test suite, reports coverage, recommends CI test config" },
      { id: "scan", label: "Scan", icon: "🔒", agent: "SecurityAgent", mcp: "security-mcp-server", input: "Source code", output: "SARIF report, CVE list", desc: "SAST, dependency CVEs, hardcoded secrets, container image vulns" },
    ],
  },
  {
    id: "ship",
    label: "Ship",
    icon: "🚢",
    color: "#0ea5e9",
    bgLight: "#e0f2fe",
    desc: "Deploy pipeline → validate → push",
    stages: [
      { id: "deploy-intent", label: "Deploy Intent", icon: "🗣️", agent: "DeployIntentAgent", mcp: "intent-mcp-server", input: "Source code + user interview", output: ".sevaforge/deployment-intent.yaml", desc: "Interactive interview — cloud, region, compute, SLOs, cost limits. Cached with SHA256 hash." },
      { id: "deploy-design", label: "Deploy Design", icon: "🎭", agent: "DeployOrchestratorAgent", mcp: "design-mcp-server", input: "deployment-intent.yaml", output: "26+ artifacts across 7 domains", desc: "Fans out to 7 persona agents in 3 parallel layers — infra, cluster, app, secrets, observability, security, cost", isPersonaStage: true },
      { id: "deploy-validate", label: "Deploy Validate", icon: "🛂", agent: "DeployValidatorAgent", mcp: "validate-mcp-server", input: "All persona artifacts + intent", output: "Validation report (PASS/BLOCK)", desc: "7 cross-checks: secrets inventory, cron validity, dates, SLOs, hash integrity, TF vars, image repo" },
      { id: "secrets", label: "Secrets", icon: "🔑", agent: "SecretsAgent", mcp: "secrets-mcp-server", input: "inventory + intent", output: "bootstrap.sh, IAM policies", desc: "Secrets bootstrap guide, IAM policy files for all service accounts" },
      { id: "lifecycle", label: "Lifecycle", icon: "♻️", agent: "LifecycleAgent", mcp: "lifecycle-mcp-server", input: "CI/CD configs", output: ".github/workflows/ chain", desc: "CI/CD lifecycle workflows — CI → Test → CD chain" },
      { id: "bridge", label: "Bridge", icon: "🌉", agent: "BridgeAgent", mcp: "github-mcp-server", input: "All generated files", output: "GitHub PR + push", desc: "Commits all artifacts, pushes to GitHub, creates PR" },
    ],
  },
];

const PERSONAS = [
  { layer: 1, id: "infra", label: "InfraArchitect", icon: "🏗️", color: "#7c3aed", output: "VPC, subnets, firewall (Terraform)" },
  { layer: 1, id: "secrets-mgr", label: "SecretsManager", icon: "🔐", color: "#7c3aed", output: "inventory.yaml, bootstrap.sh" },
  { layer: 2, id: "cluster", label: "ClusterBuilder", icon: "☸️", color: "#2563eb", output: "GKE/EKS cluster.tf" },
  { layer: 2, id: "app", label: "AppDeployer", icon: "📦", color: "#2563eb", output: "Dockerfile, Helm chart, HPA" },
  { layer: 3, id: "observability", label: "Observability", icon: "📈", color: "#059669", output: "Prometheus, Grafana, SLOs, alerts" },
  { layer: 3, id: "security", label: "Security", icon: "🛡️", color: "#059669", output: "NetworkPolicy, PodSecurity, IAM" },
  { layer: 3, id: "cost", label: "CostGuardian", icon: "💰", color: "#059669", output: "Budget alerts, shutdown, teardown" },
];

const LAYERS = [
  { id: 1, label: "Foundation", color: "#7c3aed" },
  { id: 2, label: "Platform", color: "#2563eb" },
  { id: 3, label: "Operations", color: "#059669" },
];

const DataFlowArrow = () => (
  <div className="flex items-center justify-center my-1">
    <svg width="24" height="20" viewBox="0 0 24 20">
      <path d="M12 2 L12 14 M6 10 L12 16 L18 10" stroke="#94a3b8" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </div>
);

const HorizontalArrow = () => (
  <div className="flex items-center mx-1">
    <svg width="28" height="16" viewBox="0 0 28 16">
      <path d="M2 8 L20 8 M16 4 L22 8 L16 12" stroke="#94a3b8" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </div>
);

function StageCard({ stage, phaseColor, isActive, onClick }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-lg border-2 transition-all duration-200 p-3"
      style={{
        borderColor: isActive ? phaseColor : "#e2e8f0",
        backgroundColor: isActive ? `${phaseColor}10` : "#ffffff",
        boxShadow: isActive ? `0 0 0 1px ${phaseColor}40` : "none",
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{stage.icon}</span>
        <span className="font-semibold text-sm text-gray-800">{stage.label}</span>
      </div>
      <div className="text-xs text-gray-500">{stage.agent}</div>
      {isActive && (
        <div className="mt-2 space-y-2 text-xs">
          <p className="text-gray-700">{stage.desc}</p>
          <div className="flex gap-4">
            <div>
              <span className="font-semibold text-gray-600">In: </span>
              <span className="text-gray-500">{stage.input}</span>
            </div>
          </div>
          <div>
            <span className="font-semibold text-gray-600">Out: </span>
            <span className="text-gray-500">{stage.output}</span>
          </div>
          <div className="text-gray-400 italic">MCP: {stage.mcp}</div>
        </div>
      )}
    </button>
  );
}

function PersonaPanel({ expanded }) {
  if (!expanded) return null;
  return (
    <div className="mt-3 rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-purple-50 p-4">
      <div className="text-xs font-bold text-indigo-700 mb-3 tracking-wide uppercase">
        7 Persona Agents — 3 Parallel Layers (ThreadPoolExecutor)
      </div>
      <div className="space-y-3">
        {LAYERS.map((layer) => (
          <div key={layer.id}>
            <div className="text-xs font-semibold mb-1.5" style={{ color: layer.color }}>
              Layer {layer.id}: {layer.label}
            </div>
            <div className="flex gap-2 flex-wrap">
              {PERSONAS.filter((p) => p.layer === layer.id).map((p) => (
                <div
                  key={p.id}
                  className="flex-1 min-w-[140px] rounded-lg border p-2.5"
                  style={{ borderColor: `${p.color}40`, backgroundColor: `${p.color}08` }}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span>{p.icon}</span>
                    <span className="font-semibold text-xs text-gray-800">{p.label}</span>
                  </div>
                  <div className="text-xs text-gray-500">{p.output}</div>
                </div>
              ))}
            </div>
            {layer.id < 3 && (
              <div className="flex items-center justify-center my-1">
                <svg width="120" height="16" viewBox="0 0 120 16">
                  <path d="M10 8 L110 8 M104 4 L112 8 L104 12" stroke={layer.color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeDasharray="4 3" />
                  <text x="60" y="6" textAnchor="middle" fill={layer.color} fontSize="7" fontWeight="600">waits</text>
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ArchLayer({ label, icon, color, children }) {
  return (
    <div className="rounded-xl border-2 p-4 mb-3" style={{ borderColor: `${color}60`, backgroundColor: `${color}06` }}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">{icon}</span>
        <span className="font-bold text-sm tracking-wide" style={{ color }}>{label}</span>
      </div>
      {children}
    </div>
  );
}

export default function LogicalArchitecture() {
  const [activeStage, setActiveStage] = useState(null);
  const [expandedPhase, setExpandedPhase] = useState("ship");
  const [showDataFlow, setShowDataFlow] = useState(true);

  return (
    <div className="max-w-5xl mx-auto p-6 bg-gray-50 min-h-screen font-sans">
      {/* Header */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">ForgeFlow — Logical Architecture</h1>
        <p className="text-sm text-gray-500">16 stages · 4 phases · 7 persona agents · click any stage for details</p>
      </div>

      {/* Toggle */}
      <div className="flex justify-end mb-4">
        <button
          onClick={() => setShowDataFlow(!showDataFlow)}
          className="text-xs px-3 py-1.5 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
        >
          {showDataFlow ? "Hide" : "Show"} system layers
        </button>
      </div>

      {/* System Layers (optional) */}
      {showDataFlow && (
        <div className="mb-6">
          <ArchLayer label="CLI Layer" icon="⌨️" color="#64748b">
            <div className="text-xs text-gray-600 mb-2">
              <code className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-700">forgeflow/cli/forgeflow.py</code> — argparse entry point with 16 subcommands
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span className="bg-gray-100 px-2 py-1 rounded">forgeflow run-all ./repo</span>
              <span className="bg-gray-100 px-2 py-1 rounded">forgeflow deploy-intent --path .</span>
              <span className="bg-gray-100 px-2 py-1 rounded">forgeflow dashboard</span>
            </div>
          </ArchLayer>

          <DataFlowArrow />

          <ArchLayer label="Orchestration Layer" icon="🎯" color="#6366f1">
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-white rounded-lg border p-2.5">
                <div className="font-semibold text-gray-700 mb-1">MissionControl</div>
                <div className="text-gray-500">Pipeline coordination, PIPELINE_STAGES, report saving</div>
              </div>
              <div className="bg-white rounded-lg border p-2.5">
                <div className="font-semibold text-gray-700 mb-1">Orchestrator</div>
                <div className="text-gray-500">Routes to LOCAL (importlib) or CLOUD (HTTP/SSE)</div>
              </div>
              <div className="bg-white rounded-lg border p-2.5">
                <div className="font-semibold text-gray-700 mb-1">Dashboard</div>
                <div className="text-gray-500">React UI + SSE log streaming (16 stages, 4 phases)</div>
              </div>
            </div>
          </ArchLayer>

          <DataFlowArrow />

          <div className="flex items-center justify-center gap-4 mb-3">
            <div className="flex-1 border-t border-dashed border-gray-300"></div>
            <span className="text-xs font-semibold text-gray-400 tracking-widest uppercase">MCP Protocol Layer</span>
            <div className="flex-1 border-t border-dashed border-gray-300"></div>
          </div>

          <DataFlowArrow />
        </div>
      )}

      {/* Pipeline Phases */}
      <div className="space-y-4">
        {PHASES.map((phase, phaseIdx) => {
          const isExpanded = expandedPhase === phase.id;
          return (
            <div key={phase.id}>
              {/* Phase Header */}
              <button
                onClick={() => setExpandedPhase(isExpanded ? null : phase.id)}
                className="w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-200"
                style={{
                  backgroundColor: isExpanded ? phase.bgLight : "#f8fafc",
                  border: `2px solid ${isExpanded ? phase.color : "#e2e8f0"}`,
                }}
              >
                <span className="text-xl">{phase.icon}</span>
                <div className="flex-1 text-left">
                  <span className="font-bold text-sm" style={{ color: phase.color }}>
                    Phase {phaseIdx + 1}: {phase.label}
                  </span>
                  <span className="text-xs text-gray-500 ml-3">{phase.stages.length} stages — {phase.desc}</span>
                </div>
                <div className="flex gap-1.5">
                  {phase.stages.map((s) => (
                    <span key={s.id} className="text-sm" title={s.label}>{s.icon}</span>
                  ))}
                </div>
                <svg
                  className="w-4 h-4 text-gray-400 transition-transform duration-200"
                  style={{ transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)" }}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>

              {/* Expanded Phase Content */}
              {isExpanded && (
                <div className="mt-2 pl-4 pr-2">
                  <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(phase.stages.length, 3)}, 1fr)` }}>
                    {phase.stages.map((stage) => (
                      <div key={stage.id}>
                        <StageCard
                          stage={stage}
                          phaseColor={phase.color}
                          isActive={activeStage === stage.id}
                          onClick={() => setActiveStage(activeStage === stage.id ? null : stage.id)}
                        />
                        {stage.isPersonaStage && (
                          <PersonaPanel expanded={activeStage === stage.id} />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Flow arrow between phases */}
              {phaseIdx < PHASES.length - 1 && <DataFlowArrow />}
            </div>
          );
        })}
      </div>

      {/* Data Flow Summary */}
      <div className="mt-8 rounded-xl border-2 border-gray-200 bg-white p-5">
        <h3 className="font-bold text-sm text-gray-800 mb-3">Data Flow</h3>
        <div className="flex items-center flex-wrap gap-1 text-xs">
          <span className="bg-violet-100 text-violet-700 px-2 py-1 rounded font-medium">Repository</span>
          <HorizontalArrow />
          <span className="bg-violet-50 text-violet-600 px-2 py-1 rounded">inventory.json</span>
          <HorizontalArrow />
          <span className="bg-amber-100 text-amber-700 px-2 py-1 rounded font-medium">Terraform + K8s + CI/CD</span>
          <HorizontalArrow />
          <span className="bg-green-100 text-green-700 px-2 py-1 rounded font-medium">Quality Gate</span>
          <HorizontalArrow />
          <span className="bg-sky-50 text-sky-600 px-2 py-1 rounded">deployment-intent.yaml</span>
          <HorizontalArrow />
          <span className="bg-sky-100 text-sky-700 px-2 py-1 rounded font-medium">7 Personas → 26 Artifacts</span>
          <HorizontalArrow />
          <span className="bg-sky-50 text-sky-600 px-2 py-1 rounded">Validation (7 checks)</span>
          <HorizontalArrow />
          <span className="bg-gray-800 text-white px-2 py-1 rounded font-medium">GitHub Push</span>
        </div>
      </div>

      {/* Intent Spec */}
      <div className="mt-4 rounded-xl border-2 border-gray-200 bg-white p-5">
        <h3 className="font-bold text-sm text-gray-800 mb-3">Deployment Intent — Canonical Spec</h3>
        <div className="grid grid-cols-4 gap-3 text-xs">
          {[
            { label: "Cloud", value: "GCP (default)", detail: "us-central1" },
            { label: "Compute", value: "GKE Autopilot", detail: "pay-per-pod" },
            { label: "SLOs", value: "99.5% / 500ms", detail: "availability / p99 latency" },
            { label: "Cost", value: "Shutdown 4AM–2PM", detail: "auto scale-down" },
          ].map((item) => (
            <div key={item.label} className="bg-gray-50 rounded-lg p-2.5">
              <div className="font-semibold text-gray-600">{item.label}</div>
              <div className="text-gray-800 font-medium">{item.value}</div>
              <div className="text-gray-400">{item.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-6 text-center text-xs text-gray-400">
        ForgeFlow v2.2 · 16 stages · 4 phases · 7 personas · GCP/GKE default
      </div>
    </div>
  );
}
