import graphviz

SAMPLES = [
    ("ES",1,1),("RS",1,1),("SM",1,0),("SR",1,1),("SI",1,0),("MT",1,1),
    ("BQ",1,0),("VC",1,1),("BR",1,1),("CY",1,0),("SL",1,1),("QN",1,1),
    ("TC",1,0),("RV",1,1),("ET",1,0),("QH",1,1),("EP",1,0),("HN",1,0),
]
S16 = [s for s in SAMPLES if s[1]]
SMG = [s for s in SAMPLES if s[2]]

g = graphviz.Digraph("subductcr", format="pdf")
g.attr(rankdir="TB", splines="spline", nodesep="0.18", ranksep="0.6",
       fontname="Helvetica", bgcolor="white")
g.attr("node", fontname="Helvetica", fontsize="10", style="filled",
       penwidth="0.6", color="#5F5E5A")
g.attr("edge", color="#888780", arrowsize="0.6", penwidth="0.7")

TEAL="#9FE1CB"; TEAL_D="#0F6E56"
PURP="#CECBF6"; PURP_D="#3C3489"
CORAL="#F5C4B3"; CORAL_D="#993C1D"
AMBER="#FAC775"; AMBER_D="#854F0B"
GRAY="#D3D1C7"; GRAY_D="#444441"

def node(name,label,fill,shape="box",tcolor="#2C2C2A"):
    g.node(name,label,fillcolor=fill,shape=shape,fontcolor=tcolor)

# --- input reference files ---
node("silva","silva_v132.db",GRAY,shape="note")
node("gsplus","gsplus.db",GRAY,shape="note")
node("geochem","geochem.csv",GRAY,shape="note")
node("cells","cell_counts.csv",GRAY,shape="note")

# --- 16S track fan-out ---
with g.subgraph(name="cluster_16s") as c:
    c.attr(label="16S amplicon track", color=TEAL_D, fontcolor=TEAL_D,
           style="rounded", penwidth="1")
    for name,_,_ in S16:
        node(f"qc_{name}", f"qc_16s\\n{name}", TEAL, tcolor=TEAL_D)
    node("mothur","mothur_asv\\n(merge ASVs+SILVA)",TEAL,tcolor=TEAL_D)
    node("filter","filter_normalize\\n(phyloseq)",TEAL,tcolor=TEAL_D)
    node("asvnet","asv_network\\n(igraph cliques)",TEAL,tcolor=TEAL_D)
    node("asvcg","clique_geochem\\n(VSURF)",TEAL,tcolor=TEAL_D)

for name,_,_ in S16:
    g.edge(f"qc_{name}","mothur")
g.edge("silva","mothur")
g.edge("mothur","filter"); g.edge("geochem","filter")
g.edge("filter","asvnet"); g.edge("asvnet","asvcg"); g.edge("geochem","asvcg")

# --- metagenome track fan-out ---
with g.subgraph(name="cluster_mg") as c:
    c.attr(label="Metagenome track", color=PURP_D, fontcolor=PURP_D,
           style="rounded", penwidth="1")
    for name,_,_ in SMG:
        node(f"trim_{name}", f"trim\\n{name}", PURP, tcolor=PURP_D)
        node(f"mif_{name}", f"mifaser\\n{name}", PURP, tcolor=PURP_D)
    node("genemerge","gene_merge\\n(merge+norm)",PURP,tcolor=PURP_D)
    node("genenet","gene_network\\n(gene-cliques)",PURP,tcolor=PURP_D)
    node("genecg","gene_geochem",PURP,tcolor=PURP_D)

for name,_,_ in SMG:
    g.edge(f"trim_{name}",f"mif_{name}")
    g.edge(f"mif_{name}","genemerge")
g.edge("gsplus","genemerge")  # (db feeds mifaser; simplified edge to cluster)
g.edge("genemerge","genenet"); g.edge("genenet","genecg"); g.edge("geochem","genecg")

# --- shared endpoints ---
node("nmds","nmds_adonis\\n(vegan, Fig.2)",CORAL,tcolor=CORAL_D)
node("flux","carbon_flux\\n(Eqs.1-4)",AMBER,tcolor=AMBER_D)
node("report","make_report\\n(report.html)",GRAY,shape="box",tcolor=GRAY_D)

g.edge("filter","nmds"); g.edge("geochem","nmds")
g.edge("cells","flux"); g.edge("geochem","flux")
for src in ["asvcg","genecg","nmds","flux"]:
    g.edge(src,"report")

g.render("/home/claude/subductcr_dag", cleanup=False)
g.format="png"; g.attr(dpi="130")
g.render("/home/claude/subductcr_dag_preview", cleanup=True)
print("nodes:", len(S16)+2*len(SMG)+8, "| 16S:", len(S16), "MG:", len(SMG))
