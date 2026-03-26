import graphviz
from PIL import Image, ImageDraw, ImageFont
import io

# Colors
BLUE = "#3B82F6"
GREEN = "#10B981"
ORANGE = "#F59E0B"
PURPLE = "#8B5CF6"
DARK_GRAY = "#374151"
LIGHT_GRAY = "#F3F4F6"
LIGHT_BLUE = "#DBEAFE"
WHITE = "#FFFFFF"

# Create the diagram using graphviz
dot = graphviz.Digraph(comment='ForgeFlow Architecture', format='png')
dot.attr(rankdir='TB', bgcolor=WHITE, fontname='Arial', 
         size='16,9!', ratio='fill', dpi='150',
         pad='0.5', margin='0.3')

# Title
dot.node('title', 'ForgeFlow Architecture - Deployment Models', 
         shape='plaintext', fontsize='28', fontname='Arial Bold',
         fontcolor=DARK_GRAY)

# Pipeline Flow Section
with dot.subgraph(name='cluster_pipeline') as c:
    c.attr(label='Pipeline Flow', fontsize='18', fontname='Arial Bold',
           style='rounded,filled', fillcolor=LIGHT_GRAY, color=DARK_GRAY)
    
    # Pipeline stages
    stages = [
        ('DISCOVER', 'discovery-mcp', 'DiscoveryAgent'),
        ('NORMALIZE', 'normalize-mcp', 'NormalizationAgent'),
        ('DOCS', 'docs-mcp', 'DocumentationAgent'),
        ('GENERATE', 'diagram-generator-mcp', 'GenerationAgent'),
        ('SCAN', 'security-mcp', 'SecurityAgent'),
        ('APPROVAL', 'approval-mcp', 'ApprovalGate'),
        ('BRIDGE', 'deployment-mcp', 'BridgeAgent'),
    ]
    
    prev = None
    for i, (name, mcp, agent) in enumerate(stages):
        label = f'<<B>{name}</B><BR/><FONT POINT-SIZE="10">{mcp}</FONT><BR/><FONT POINT-SIZE="9" COLOR="#666666">{agent}</FONT>>'
        node_id = f'stage_{i}'
        c.node(node_id, label, shape='box', style='rounded,filled', 
               fillcolor=BLUE if name != 'APPROVAL' else '#FCD34D',
               fontcolor=WHITE if name != 'APPROVAL' else DARK_GRAY,
               fontname='Arial', width='1.3', height='0.8')
        if prev:
            c.edge(prev, node_id, color=DARK_GRAY, penwidth='2')
        prev = node_id
    
    # GitHub at the end
    c.node('github_pipe', '<<B>GitHub</B>>', shape='box', style='rounded,filled',
           fillcolor=DARK_GRAY, fontcolor=WHITE, fontname='Arial', width='1', height='0.6')
    c.edge(prev, 'github_pipe', color=DARK_GRAY, penwidth='2')

# Invisible edge to position pipeline below title
dot.edge('title', 'stage_0', style='invis')

# Deployment Models Section - Three columns
with dot.subgraph(name='cluster_deployments') as d:
    d.attr(label='Deployment Models', fontsize='18', fontname='Arial Bold',
           style='rounded', color=DARK_GRAY)
    
    # LOCAL MODE
    with d.subgraph(name='cluster_local') as local:
        local.attr(label='🏠 LOCAL MODE', fontsize='16', fontname='Arial Bold',
                   style='rounded,filled', fillcolor=BLUE, fontcolor=WHITE)
        
        with local.subgraph(name='cluster_local_mac') as mac:
            mac.attr(label="User's Mac", fontsize='12', fontname='Arial',
                     style='rounded,filled', fillcolor=LIGHT_GRAY, color=DARK_GRAY)
            
            mac.node('local_cli', '<<B>ForgeFlow CLI</B>>', shape='box', 
                     style='rounded,filled', fillcolor=ORANGE, fontcolor=WHITE,
                     fontname='Arial', width='1.5')
            
            # MCP Servers
            mac.node('local_mcps', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="3" BGCOLOR="#3B82F6"><FONT COLOR="white"><B>MCP Servers</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#60A5FA">discovery-mcp</TD><TD BGCOLOR="#60A5FA">normalize-mcp</TD><TD BGCOLOR="#60A5FA">security-mcp</TD></TR>
                <TR><TD BGCOLOR="#60A5FA">deployment-mcp</TD><TD BGCOLOR="#60A5FA">diagram-gen-mcp</TD><TD BGCOLOR="#60A5FA">github-mcp</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            # Agents
            mac.node('local_agents', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="3" BGCOLOR="#3B82F6"><FONT COLOR="white"><B>Agents</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#60A5FA">DiscoveryAgent</TD><TD BGCOLOR="#60A5FA">NormalizationAgent</TD><TD BGCOLOR="#60A5FA">SecurityAgent</TD></TR>
                <TR><TD BGCOLOR="#60A5FA">GenerationAgent</TD><TD BGCOLOR="#60A5FA">DocumentationAgent</TD><TD BGCOLOR="#60A5FA">BridgeAgent</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            mac.edge('local_cli', 'local_mcps', style='invis')
            mac.edge('local_mcps', 'local_agents', style='invis')
        
        local.node('local_git', 'Local Git Repo', shape='box', style='rounded,filled',
                   fillcolor=LIGHT_GRAY, fontcolor=DARK_GRAY, fontname='Arial')
        local.node('local_github', '<<B>GitHub</B>>', shape='box', style='rounded,filled',
                   fillcolor=DARK_GRAY, fontcolor=WHITE, fontname='Arial')
        local.node('local_note', '"Everything runs on your machine"', shape='plaintext',
                   fontsize='10', fontname='Arial Italic', fontcolor='#666666')
        
        local.edge('local_agents', 'local_git', color=DARK_GRAY)
        local.edge('local_git', 'local_github', color=DARK_GRAY)
    
    # HYBRID MODE
    with d.subgraph(name='cluster_hybrid') as hybrid:
        hybrid.attr(label='🔀 HYBRID MODE', fontsize='16', fontname='Arial Bold',
                    style='rounded,filled', fillcolor=PURPLE, fontcolor=WHITE)
        
        with hybrid.subgraph(name='cluster_hybrid_mac') as mac:
            mac.attr(label="User's Mac", fontsize='12', fontname='Arial',
                     style='rounded,filled', fillcolor=LIGHT_GRAY, color=DARK_GRAY)
            
            mac.node('hybrid_cli', '<<B>ForgeFlow CLI</B>>', shape='box',
                     style='rounded,filled', fillcolor=ORANGE, fontcolor=WHITE,
                     fontname='Arial', width='1.5')
            
            mac.node('hybrid_local_mcps', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="2" BGCOLOR="#3B82F6"><FONT COLOR="white"><B>Local MCPs</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#60A5FA">discovery-mcp</TD><TD BGCOLOR="#60A5FA">normalize-mcp</TD></TR>
                <TR><TD BGCOLOR="#60A5FA" COLSPAN="2">deployment-mcp</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            mac.node('hybrid_local_agents', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD BGCOLOR="#3B82F6"><FONT COLOR="white"><B>Local Agents</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#60A5FA">DiscoveryAgent, NormalizationAgent</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            mac.edge('hybrid_cli', 'hybrid_local_mcps', style='invis')
            mac.edge('hybrid_local_mcps', 'hybrid_local_agents', style='invis')
        
        with hybrid.subgraph(name='cluster_hybrid_cloud') as cloud:
            cloud.attr(label='Cloud/Public', fontsize='12', fontname='Arial',
                       style='rounded,filled', fillcolor=LIGHT_BLUE, color=GREEN)
            
            cloud.node('hybrid_public_mcps', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="2" BGCOLOR="#10B981"><FONT COLOR="white"><B>Public MCPs</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">GitHub MCP</TD><TD BGCOLOR="#6EE7B7">Security Scanning MCP</TD></TR>
                <TR><TD BGCOLOR="#6EE7B7" COLSPAN="2">(Snyk/Trivy)</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            cloud.node('hybrid_public_agents', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD BGCOLOR="#10B981"><FONT COLOR="white"><B>Public Agents</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">SecurityAgent, BridgeAgent</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            cloud.edge('hybrid_public_mcps', 'hybrid_public_agents', style='invis')
        
        hybrid.node('hybrid_note', '"Mix of local + public services"', shape='plaintext',
                    fontsize='10', fontname='Arial Italic', fontcolor='#666666')
        
        hybrid.edge('hybrid_local_agents', 'hybrid_public_mcps', dir='both', color=PURPLE, penwidth='2')
    
    # PUBLIC MODE
    with d.subgraph(name='cluster_public') as public:
        public.attr(label='☁️ PUBLIC MODE', fontsize='16', fontname='Arial Bold',
                    style='rounded,filled', fillcolor=GREEN, fontcolor=WHITE)
        
        with public.subgraph(name='cluster_public_mac') as mac:
            mac.attr(label="User's Mac", fontsize='12', fontname='Arial',
                     style='rounded,filled', fillcolor=LIGHT_GRAY, color=DARK_GRAY)
            
            mac.node('public_cli', '<<B>ForgeFlow CLI</B>>', shape='box',
                     style='rounded,filled', fillcolor=ORANGE, fontcolor=WHITE,
                     fontname='Arial', width='1.5')
        
        with public.subgraph(name='cluster_public_cloud') as cloud:
            cloud.attr(label='Cloud/Public', fontsize='12', fontname='Arial',
                       style='rounded,filled', fillcolor=LIGHT_BLUE, color=GREEN)
            
            cloud.node('public_mcps', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="3" BGCOLOR="#10B981"><FONT COLOR="white"><B>All MCP Servers</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">discovery-mcp</TD><TD BGCOLOR="#6EE7B7">normalize-mcp</TD><TD BGCOLOR="#6EE7B7">security-mcp</TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">deployment-mcp</TD><TD BGCOLOR="#6EE7B7">diagram-gen-mcp</TD><TD BGCOLOR="#6EE7B7">github-mcp</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            cloud.node('public_agents', '''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
                <TR><TD COLSPAN="3" BGCOLOR="#10B981"><FONT COLOR="white"><B>All Agents</B></FONT></TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">DiscoveryAgent</TD><TD BGCOLOR="#6EE7B7">NormalizationAgent</TD><TD BGCOLOR="#6EE7B7">SecurityAgent</TD></TR>
                <TR><TD BGCOLOR="#6EE7B7">GenerationAgent</TD><TD BGCOLOR="#6EE7B7">DocumentationAgent</TD><TD BGCOLOR="#6EE7B7">BridgeAgent</TD></TR>
            </TABLE>>''', shape='plaintext')
            
            cloud.edge('public_mcps', 'public_agents', style='invis')
        
        public.node('public_note', '"MCPs & Agents hosted publicly"', shape='plaintext',
                    fontsize='10', fontname='Arial Italic', fontcolor='#666666')
        
        public.edge('public_cli', 'public_mcps', color=GREEN, penwidth='2')

# Position the three deployment models side by side
dot.edge('github_pipe', 'local_cli', style='invis')
dot.edge('local_cli', 'hybrid_cli', style='invis', constraint='false')
dot.edge('hybrid_cli', 'public_cli', style='invis', constraint='false')

# Same rank for deployment headers
with dot.subgraph() as s:
    s.attr(rank='same')
    s.node('local_cli')
    s.node('hybrid_cli')
    s.node('public_cli')

# Render
dot.render('/home/ubuntu/forgeflow_architecture', cleanup=True)
print("Diagram created: /home/ubuntu/forgeflow_architecture.png")
