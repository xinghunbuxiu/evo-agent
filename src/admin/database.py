"""
MySQL 数据库模块 - 用户登录管理
支持 Gitee Token 和 账号密码 两种登录方式
"""

import os
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

# 同步 MySQL 连接
try:
    import pymysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


def hash_password(password: str) -> str:
    """密码哈希（使用 SHA256 + salt）"""
    salt = os.getenv("PASSWORD_SALT", "evo-salt-2024")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


class Database:
    """MySQL 数据库管理"""
    
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.user = os.getenv("DB_USER", "evo_user")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "evo_db")
        self._connection = None
        self._local_store_path = Path(
            os.getenv(
                "EVO_LOCAL_AUTH_DB",
                str(Path(__file__).resolve().parents[2] / ".local_admin_users.json"),
            )
        )
    
    def _get_connection(self):
        """获取数据库连接"""
        if not MYSQL_AVAILABLE:
            raise RuntimeError("pymysql 未安装，请运行: pip install pymysql")
        
        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
        return self._connection
    
    def init_tables(self):
        """初始化数据库和表（自动创建）"""
        if not MYSQL_AVAILABLE:
            self._ensure_local_store()
            return

        # 1. 先连接 MySQL（不指定数据库）创建数据库
        conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            charset='utf8mb4'
        )
        
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
        conn.close()
        
        # 2. 再连接到具体数据库创建表（支持账号密码和 Gitee 两种登录方式）
        conn = self._get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) UNIQUE,
                    password_hash VARCHAR(64),
                    gitee_id INT UNIQUE,
                    login VARCHAR(100),
                    name VARCHAR(100),
                    avatar_url VARCHAR(500),
                    token_hash VARCHAR(64),
                    login_type ENUM('password', 'gitee') DEFAULT 'password',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_username (username),
                    INDEX idx_gitee_id (gitee_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.commit()
    
    def _ensure_local_store(self):
        """初始化本地账号存储（无 MySQL 时兜底）"""
        if self._local_store_path.is_file():
            return
        self._local_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._local_store_path.write_text(
            json.dumps({"users": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_local_store(self) -> Dict[str, Any]:
        self._ensure_local_store()
        try:
            return json.loads(self._local_store_path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": []}

    def _save_local_store(self, data: Dict[str, Any]):
        self._local_store_path.parent.mkdir(parents=True, exist_ok=True)
        self._local_store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_local_user(self, username: str) -> Optional[Dict[str, Any]]:
        store = self._load_local_store()
        return next((u for u in store.get("users", []) if u.get("username") == username), None)

    def _create_local_user(self, username: str, password: str) -> bool:
        store = self._load_local_store()
        if any(u.get("username") == username for u in store.get("users", [])):
            return False
        next_id = max((u.get("id", 0) for u in store.get("users", [])), default=0) + 1
        store["users"].append({
            "id": next_id,
            "username": username,
            "password_hash": hash_password(password),
            "name": username,
            "login_type": "password",
        })
        self._save_local_store(store)
        return True

    def _verify_local_password(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self._find_local_user(username)
        if not user or user.get("password_hash") != hash_password(password):
            return None
        return {
            "id": user["id"],
            "login": user["username"],
            "name": user.get("name") or username,
        }
    
    def _hash_token(self, token: str) -> str:
        """对 Token 进行哈希存储（安全）"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    async def verify_gitee_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证 Gitee Token 并返回用户信息
        同时检查/更新数据库中的用户记录
        """
        # 1. 调用 Gitee API 验证 Token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://gitee.com/api/v5/user",
                headers={"Authorization": f"token {token}"}
            )
            
            if resp.status_code != 200:
                return None
            
            user_info = resp.json()
        
        # 2. 同步到数据库
        try:
            self._sync_user(user_info, token)
        except Exception as e:
            print(f"[DB Warning] 用户同步失败: {e}")
        
        return {
            "id": user_info.get("id"),
            "login": user_info.get("login"),
            "name": user_info.get("name"),
            "avatar": user_info.get("avatar_url"),
            "token": token,  # 返回原始 token 用于后续 Gitee 操作
        }
    
    def _sync_user(self, user_info: dict, token: str):
        """同步用户到数据库"""
        conn = self._get_connection()
        with conn.cursor() as cursor:
            token_hash = self._hash_token(token)
            
            # 检查用户是否存在
            cursor.execute(
                "SELECT id FROM users WHERE gitee_id = %s",
                (user_info.get("id"),)
            )
            result = cursor.fetchone()
            
            if result:
                # 更新用户信息和 Token
                cursor.execute(
                    """UPDATE users SET 
                        login = %s, name = %s, avatar_url = %s, token_hash = %s
                        WHERE gitee_id = %s
                    """,
                    (
                        user_info.get("login"),
                        user_info.get("name"),
                        user_info.get("avatar_url"),
                        token_hash,
                        user_info.get("id")
                    )
                )
            else:
                # 插入新用户
                cursor.execute(
                    """INSERT INTO users 
                        (gitee_id, login, name, avatar_url, token_hash)
                        VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_info.get("id"),
                        user_info.get("login"),
                        user_info.get("name"),
                        user_info.get("avatar_url"),
                        token_hash
                    )
                )
            
            conn.commit()
    
    def get_user_by_gitee_id(self, gitee_id: int) -> Optional[Dict[str, Any]]:
        """通过 Gitee ID 获取用户信息"""
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE gitee_id = %s",
                    (gitee_id,)
                )
                return cursor.fetchone()
        except Exception as e:
            print(f"[DB Error] 查询用户失败: {e}")
            return None
    
    def create_user(self, username: str, password: str) -> bool:
        """创建新用户（账号密码方式）"""
        if not MYSQL_AVAILABLE:
            return self._create_local_user(username, password)

        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # 检查用户名是否已存在
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return False
                
                # 创建用户
                password_hash = hash_password(password)
                cursor.execute(
                    """INSERT INTO users 
                        (username, password_hash, name, login_type)
                        VALUES (%s, %s, %s, 'password')
                    """,
                    (username, password_hash, username)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"[DB Error] 创建用户失败: {e}")
            print("[DB Fallback] 改用本地账号存储")
            return self._create_local_user(username, password)
    
    def verify_password(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """验证账号密码，返回用户信息"""
        if not MYSQL_AVAILABLE:
            return self._verify_local_password(username, password)

        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                password_hash = hash_password(password)
                cursor.execute(
                    """SELECT id, username, name FROM users 
                        WHERE username = %s AND password_hash = %s AND login_type = 'password'
                    """,
                    (username, password_hash)
                )
                result = cursor.fetchone()
                print(f"[Debug] 查询结果: {result}")
                if result:
                    # DictCursor 返回字典
                    return {
                        "id": result["id"] if isinstance(result, dict) else result[0],
                        "login": result["username"] if isinstance(result, dict) else result[1],
                        "name": (result["name"] if isinstance(result, dict) else result[2]) or username,
                    }
                return None
        except Exception as e:
            print(f"[DB Error] 验证密码失败: {e}")
            import traceback
            traceback.print_exc()
            print("[DB Fallback] 改用本地账号存储")
            return self._verify_local_password(username, password)
    
    def close(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None


# 全局数据库实例
db = Database()
