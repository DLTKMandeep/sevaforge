# SevaForge Architecture Diagrams

Open-source, version-controllable architecture diagrams in two formats.

## Files

| File | Format | Description |
|------|--------|-------------|
| `sevaforge-architecture-local.mermaid` | Mermaid | 9-layer local development architecture |
| `sevaforge-cloud-gcp.mermaid` | Mermaid | GCP cloud deployment (GKE, Vertex AI, AlloyDB) |
| `sevaforge-cloud-aws.mermaid` | Mermaid | AWS cloud deployment (EKS, Bedrock, Aurora) |
| `sevaforge-cloud-azure.mermaid` | Mermaid | Azure cloud deployment (AKS, Azure OpenAI, Azure PG) |
| `sevaforge-selfhosted-oss.mermaid` | Mermaid | Self-hosted OSS deployment (k3s, Ollama, LiteLLM) |
| `sevaforge-deploy-flow.mermaid` | Mermaid | 17-step deploy flow sequence diagram (end-to-end walk-through) |
| `sevaforge-architecture-local.d2` | D2 | Local architecture with nested containers |

## Rendering

### Mermaid (recommended for GitHub/GitLab)

**Option 1 — GitHub native** (just push `.mermaid` files — GitHub renders them automatically)

**Option 2 — CLI rendering:**
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i sevaforge-architecture-local.mermaid -o sevaforge-local.svg
mmdc -i sevaforge-cloud-gcp.mermaid -o sevaforge-gcp.svg -t dark
```

**Option 3 — VS Code:**  
Install the "Mermaid Preview" extension, then open any `.mermaid` file.

**Option 4 — Live editor:**  
Paste contents into [mermaid.live](https://mermaid.live)

### D2 (Terrastruct)

```bash
# Install (macOS)
brew install d2

# Install (Linux)
curl -fsSL https://d2lang.com/install.sh | sh -s --

# Render
d2 sevaforge-architecture-local.d2 sevaforge-local.svg
d2 --theme 200 sevaforge-architecture-local.d2 sevaforge-dark.svg
d2 --layout elk sevaforge-architecture-local.d2 sevaforge-elk.svg
```

**Live editor:** Paste contents into [play.d2lang.com](https://play.d2lang.com)

## Embedding in Markdown

```markdown
# In GitHub README:
![SevaForge Architecture](docs/diagrams/sevaforge-architecture-local.mermaid)

# Or inline with fenced code block:
```mermaid
graph TB
  subgraph L1["Layer 1"]
    ...
  end
```‎
```

## Editing Tips

- **Mermaid:** Use `classDef` + `class` for consistent color themes per layer
- **D2:** Use nested containers (`L1: { ... }`) for the layer grouping pattern
- Both formats are plain text — perfect for code review and git diffs
