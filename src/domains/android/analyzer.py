"""Android 分析器（占位）"""
from pathlib import Path

class AndroidAnalyzer:
    def __init__(self, workspace: Path, tenant_id: str = "default"):
        self.workspace = workspace
        self.tenant_id = tenant_id
    
    def analyze_apk(self, apk_path: Path) -> dict:
        return {"status": "placeholder", "domain": "android"}
