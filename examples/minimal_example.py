from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prg27 import PRG27, plate_details

OUT = Path(__file__).with_name("minimal_project_graph.prg")
g = PRG27()
g.tags = ["example", "ProjectGraph"]
g.node("a", "问题", 100, 100, 260, 90, color=(40,90,150,0.18), weight="600")
g.node("b", "方案", 620, 100, 260, 90, color=(40,120,95,0.18), weight="600")
g.line("a", "b", "通过分析\n得到", color=(120,160,190,0.96))
g.node("c", "验证", 620, 420, 260, 90, color=(110,80,145,0.18), weight="600")
g.line("b", "c", "落地后\n验证", color=(160,130,195,0.96))
g.arc("c", "a", "反馈修正", offset=260, line_type="dashed", color=(90,165,130,0.96))
g.section("s", "问题解决闭环", ["a","b","c"], color=(70,100,130,0.05), border="dashed")
g.readme = "Project Graph Architect skill smoke example"
g.write(OUT)
print(OUT)
