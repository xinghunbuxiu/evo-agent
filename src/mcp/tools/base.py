"""
Tool 基类
所有 RestoreX Tools 都继承此类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ToolParameter:
    """Tool 参数定义"""
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[list] = None


class BaseTool(ABC):
    """Tool 基类"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool 名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool 描述"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> list:
        """参数定义列表"""
        pass
    
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Tool"""
        pass
    
    def get_definition(self) -> Dict[str, Any]:
        """获取 MCP Tool 定义"""
        props = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            
            props[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required
            }
        }
    
    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """验证参数，返回错误信息或 None"""
        for param in self.parameters:
            if param.required and param.name not in params:
                return f"缺少必填参数: {param.name}"
            
            if param.enum and param.name in params:
                value = params[param.name]
                if value not in param.enum:
                    return f"参数 {param.name} 必须是 {param.enum} 之一"
        
        return None
