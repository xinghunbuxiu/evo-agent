"""
Evo - 任务队列系统

支持异步任务处理、状态追踪、多项目并发
"""

from __future__ import annotations

import json
import uuid
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 执行中
    SUCCESS = "success"      # 成功完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 取消


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Task:
    """任务定义"""
    id: str
    type: str                          # 任务类型: analyze, reconstruct, sync, etc
    payload: Dict[str, Any]            # 任务数据
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    tenant_id: str = "default"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: float = 0.0             # 0-100
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority.value,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Task:
        return cls(
            id=data["id"],
            type=data["type"],
            payload=data["payload"],
            status=TaskStatus(data["status"]),
            priority=TaskPriority(data["priority"]),
            tenant_id=data.get("tenant_id", "default"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            progress=data.get("progress", 0.0),
        )


class TaskQueue:
    """
    任务队列管理器
    
    支持:
    - 优先级队列
    - 并发执行控制
    - 持久化存储
    - 实时状态追踪
    """
    
    def __init__(self, workspace: Path, max_workers: int = 3):
        self.workspace = workspace
        self.max_workers = max_workers
        
        # 队列目录
        self.queue_dir = workspace / ".queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存队列 (优先级队列)
        self._queue = queue.PriorityQueue()
        
        # 正在执行的任务
        self._running: Dict[str, Task] = {}
        
        # 任务处理器映射
        self._handlers: Dict[str, Callable] = {}
        
        # 执行器线程池
        self._executor = threading.Thread(target=self._process_loop, daemon=True)
        self._stop_event = threading.Event()
        
        # 加载持久化的待处理任务
        self._load_pending_tasks()
    
    def start(self):
        """启动队列处理器"""
        self._executor.start()
    
    def stop(self):
        """停止队列处理器"""
        self._stop_event.set()
        self._executor.join(timeout=5)
    
    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理器"""
        self._handlers[task_type] = handler
    
    def submit(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        tenant_id: str = "default"
    ) -> Task:
        """
        提交任务到队列
        
        Args:
            task_type: 任务类型 (必须已注册处理器)
            payload: 任务数据
            priority: 优先级
            tenant_id: 租户ID
        
        Returns:
            创建的任务对象
        """
        task = Task(
            id=str(uuid.uuid4())[:8],
            type=task_type,
            payload=payload,
            priority=priority,
            tenant_id=tenant_id,
        )
        
        # 持久化
        self._save_task(task)
        
        # 加入内存队列 (优先级越低数字越小，所以用负数)
        self._queue.put((-priority.value, task.created_at, task))
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务状态"""
        # 先查运行中
        if task_id in self._running:
            return self._running[task_id]
        
        # 查持久化
        task_file = self.queue_dir / f"{task_id}.json"
        if task_file.exists():
            with open(task_file) as f:
                return Task.from_dict(json.load(f))
        
        return None
    
    def list_tasks(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100
    ) -> List[Task]:
        """列出任务"""
        tasks = []
        
        for task_file in sorted(self.queue_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(task_file) as f:
                    task = Task.from_dict(json.load(f))
                
                # 过滤
                if tenant_id and task.tenant_id != tenant_id:
                    continue
                if status and task.status != status:
                    continue
                
                tasks.append(task)
                if len(tasks) >= limit:
                    break
            except:
                pass
        
        return tasks
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        # 如果在运行中，无法取消（只能标记）
        if task_id in self._running:
            return False
        
        # 更新状态
        task = self.get_task(task_id)
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            self._save_task(task)
            return True
        
        return False
    
    def update_progress(self, task_id: str, progress: float, message: Optional[str] = None):
        """更新任务进度"""
        if task_id in self._running:
            task = self._running[task_id]
            task.progress = min(100.0, max(0.0, progress))
            if message:
                task.result = task.result or {}
                task.result["message"] = message
            self._save_task(task)
    
    def _process_loop(self):
        """队列处理主循环"""
        while not self._stop_event.is_set():
            try:
                # 检查并发限制
                if len(self._running) >= self.max_workers:
                    self._stop_event.wait(0.1)
                    continue
                
                # 获取任务 (最多等待1秒)
                try:
                    _, _, task = self._queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # 检查是否已取消
                if task.status == TaskStatus.CANCELLED:
                    continue
                
                # 执行任务
                self._execute_task(task)
                
            except Exception as e:
                print(f"Queue processing error: {e}")
    
    def _execute_task(self, task: Task):
        """执行任务"""
        # 获取处理器
        handler = self._handlers.get(task.type)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"No handler for task type: {task.type}"
            self._save_task(task)
            return
        
        # 更新状态
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()
        self._running[task.id] = task
        self._save_task(task)
        
        # 在后台线程执行
        def run_task():
            try:
                # 调用处理器
                result = handler(task)
                
                # 更新成功状态
                task.status = TaskStatus.SUCCESS
                task.result = result if isinstance(result, dict) else {"data": result}
                task.progress = 100.0
                
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
            finally:
                task.completed_at = datetime.now().isoformat()
                self._save_task(task)
                del self._running[task.id]
        
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
    
    def _save_task(self, task: Task):
        """持久化任务"""
        task_file = self.queue_dir / f"{task.id}.json"
        with open(task_file, "w") as f:
            json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _load_pending_tasks(self):
        """加载持久化的待处理任务"""
        for task_file in self.queue_dir.glob("*.json"):
            try:
                with open(task_file) as f:
                    task = Task.from_dict(json.load(f))
                
                # 只加载 pending 状态的任务
                if task.status == TaskStatus.PENDING:
                    self._queue.put((-task.priority.value, task.created_at, task))
            except:
                pass


# 全局队列实例
_queue_instances: Dict[str, TaskQueue] = {}


def get_task_queue(workspace: Path, max_workers: int = 3) -> TaskQueue:
    """获取任务队列实例（单例）"""
    key = str(workspace.resolve())
    if key not in _queue_instances:
        _queue_instances[key] = TaskQueue(workspace, max_workers)
    return _queue_instances[key]


# 常用任务类型常量
TASK_ANALYZE = "analyze"
TASK_RECONSTRUCT = "reconstruct"
TASK_SYNC_CLOUD = "sync_cloud"
TASK_GENERATE_SKILL = "generate_skill"
TASK_VALIDATE_SKILL = "validate_skill"
TASK_PUBLISH_SKILL = "publish_skill"
