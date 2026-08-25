"""PC 二进制分析器（占位）"""
from pathlib import Path

class PCAnalyzer:
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
    
    def analyze_binary(self, binary_path: Path) -> dict:
        return {"status": "placeholder", "domain": "pc"}
