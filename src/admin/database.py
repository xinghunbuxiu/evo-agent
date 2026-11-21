"""
MySQL 数据库模块 - 用户登录管理
支持 Gitee Token 和 账号密码 两种登录方式
"""

import os
import base64
import fcntl
from contextlib import contextmanager
import hashlib
import hmac
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

_PASSWORD_HASH_ITERATIONS = 310_000
_PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
_LEGACY_PASSWORD_SALT = "evo-salt-2024"


def _legacy_hash_password(password: str) -> str:
    """仅用于验证历史 SHA-256 密码；成功登录后必须升级。"""
    salt = os.getenv("PASSWORD_SALT", _LEGACY_PASSWORD_SALT)
    return hashlib.sha256(f"{password}{salt}".encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """使用每个密码独立随机盐的 PBKDF2-HMAC-SHA256 格式。"""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PASSWORD_HASH_ITERATIONS
    )
    return "$".join((
        _PASSWORD_HASH_ALGORITHM,
        str(_PASSWORD_HASH_ITERATIONS),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    ))


def verify_password_hash(password: str, encoded: str) -> tuple[bool, bool]:
    """返回 (是否匹配, 是否需要升级)。未知格式和损坏数据均失败关闭。"""
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False, False

    if encoded.startswith(_PASSWORD_HASH_ALGORITHM + "$"):
        try:
            algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
            iterations = int(iterations_text)
            if algorithm != _PASSWORD_HASH_ALGORITHM or not 100_000 <= iterations <= 2_000_000:
                return False, False
            salt = base64.b64decode(salt_text.encode("ascii"), altchars=b"-_", validate=True)
            expected = base64.b64decode(digest_text.encode("ascii"), altchars=b"-_", validate=True)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            if len(salt) < 16 or len(expected) != 32:
                return False, False
            matched = hmac.compare_digest(actual, expected)
            return matched, matched and iterations < _PASSWORD_HASH_ITERATIONS
        except (ValueError, TypeError, UnicodeError):
            return False, False

    # 旧版本存储 SHA-256(password + salt)，只允许在成功验证后升级。
    if len(encoded) == 64:
        matched = hmac.compare_digest(_legacy_hash_password(password), encoded.lower())
        return matched, matched
    return False, False


def _resolve_local_auth_store_path() -> Path:
    """将本地认证数据放在仓库之外；支持显式路径和 XDG 数据目录。"""
    explicit_path = str(os.getenv("EVO_LOCAL_AUTH_DB") or "").strip()
    if explicit_path:
        return Path(explicit_path).expanduser()
    data_home = str(os.getenv("XDG_DATA_HOME") or "").strip()
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "evo" / "admin_users.json"

# 同步 MySQL 连接
try:
    import pymysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


class AuthStorageUnavailable(RuntimeError):
    """Configured authentication storage is unavailable; no fallback is permitted."""


class Database:
    """认证存储访问；实例生命周期内只使用一个后端。"""

    def __init__(
        self,
        local_store_path: Optional[Path] = None,
        legacy_store_path: Optional[Path] = None,
        backend: Optional[str] = None,
    ):
        configured_backend = str(backend or os.getenv("EVO_AUTH_BACKEND") or "").strip().lower()
        if not configured_backend:
            configured_backend = "mysql" if MYSQL_AVAILABLE else "local"
        if configured_backend not in {"mysql", "local"}:
            raise ValueError("EVO_AUTH_BACKEND must be 'mysql' or 'local'")
        self.backend = configured_backend
        self.host = os.getenv("DB_HOST", "localhost")
        # Local auth does not consume MySQL settings; malformed DB_PORT must not block it.
        self.port = int(os.getenv("DB_PORT", "3306")) if self.backend == "mysql" else None
        self.user = os.getenv("DB_USER", "evo_user")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "evo_db")
        self._connection = None
        self._local_store_path = Path(local_store_path) if local_store_path else _resolve_local_auth_store_path()
        self._legacy_local_store_path = (
            Path(legacy_store_path) if legacy_store_path
            else Path(__file__).resolve().parents[2] / ".local_admin_users.json"
        )
    
    def _get_connection(self):
        """获取数据库连接"""
        if self.backend != "mysql":
            raise RuntimeError("当前认证后端为本地文件，不能访问 MySQL")
        if not MYSQL_AVAILABLE:
            raise AuthStorageUnavailable("认证后端配置为 MySQL，但 pymysql 未安装")
        
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
        if self.backend == "local":
            self._ensure_local_store()
            return
        if not MYSQL_AVAILABLE:
            raise AuthStorageUnavailable("认证后端配置为 MySQL，但 pymysql 未安装")

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
                    password_hash VARCHAR(255),
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
            # Existing deployments may still have the legacy 64-character column.
            cursor.execute(
                """SELECT CHARACTER_MAXIMUM_LENGTH AS max_length
                   FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE()
                     AND TABLE_NAME = 'users'
                     AND COLUMN_NAME = 'password_hash'"""
            )
            column = cursor.fetchone()
            max_length = (
                column.get("max_length") if isinstance(column, dict)
                else column[0] if column else None
            )
            if max_length is not None and int(max_length) < 255:
                cursor.execute("ALTER TABLE users MODIFY password_hash VARCHAR(255) NULL")
            conn.commit()

    def _ensure_local_store(self):
        """初始化本地认证文件；旧仓库路径只读迁移，不删除源文件。"""
        if self._local_store_path.is_file():
            return
        if self._legacy_local_store_path != self._local_store_path and self._legacy_local_store_path.is_file():
            try:
                legacy_data = json.loads(self._legacy_local_store_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Legacy local auth store cannot be read; refusing to replace it") from exc
            if not isinstance(legacy_data, dict) or not isinstance(legacy_data.get("users"), list):
                raise RuntimeError("Legacy local auth store has an invalid schema; refusing to replace it")
            self._save_local_store(legacy_data)
            return
        self._save_local_store({"users": []})

    @contextmanager
    def _local_store_lock(self):
        """跨进程串行化本地账号文件的读改写与首次迁移。"""
        self._local_store_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self._local_store_path.with_name(f"{self._local_store_path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_local_store_unlocked(self) -> Dict[str, Any]:
        """调用方必须持有本地存储锁。"""
        self._ensure_local_store()
        try:
            data = json.loads(self._local_store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Local auth store is unreadable; refusing to reset account data") from exc
        if not isinstance(data, dict) or not isinstance(data.get("users"), list):
            raise RuntimeError("Local auth store has an invalid schema; refusing to reset account data")
        return data

    def _load_local_store(self) -> Dict[str, Any]:
        with self._local_store_lock():
            return self._load_local_store_unlocked()

    def _save_local_store(self, data: Dict[str, Any]):
        if not isinstance(data, dict) or not isinstance(data.get("users"), list):
            raise ValueError("Local auth store must contain a users list")
        self._local_store_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._local_store_path.parent,
                prefix=f".{self._local_store_path.name}.", delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self._local_store_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _find_local_user(self, username: str) -> Optional[Dict[str, Any]]:
        store = self._load_local_store()
        return next((u for u in store.get("users", []) if u.get("username") == username), None)

    def _create_local_user(self, username: str, password: str) -> bool:
        with self._local_store_lock():
            store = self._load_local_store_unlocked()
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
        with self._local_store_lock():
            store = self._load_local_store_unlocked()
            user = next((item for item in store["users"] if item.get("username") == username), None)
            if not user:
                return None
            matched, needs_upgrade = verify_password_hash(password, user.get("password_hash"))
            if not matched:
                return None
            if needs_upgrade:
                user["password_hash"] = hash_password(password)
                self._save_local_store(store)
            return {
                "id": user["id"],
                "auth_provider": "password",
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
            "auth_provider": "gitee",
            "login": user_info.get("login"),
            "name": user_info.get("name"),
            "avatar": user_info.get("avatar_url"),
            "token": token,  # 返回原始 token 用于后续 Gitee 操作
        }
    
    def _sync_user(self, user_info: dict, token: str):
        """同步用户到数据库"""
        if self.backend == "local":
            return
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
        if self.backend != "mysql":
            return None
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
        """只向实例选定的认证后端创建账号；后端故障时明确失败。"""
        if self.backend == "local":
            return self._create_local_user(username, password)
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    return False
                cursor.execute(
                    """INSERT INTO users
                        (username, password_hash, name, login_type)
                        VALUES (%s, %s, %s, 'password')
                    """,
                    (username, hash_password(password), username)
                )
                conn.commit()
                return True
        except Exception as exc:
            raise AuthStorageUnavailable("认证数据库暂时不可用") from exc
    
    def verify_password(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """只从实例选定的认证后端验证账号；后端故障时明确失败。"""
        if self.backend == "local":
            return self._verify_local_password(username, password)
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT id, username, name, password_hash FROM users
                       WHERE username = %s AND login_type = 'password'""",
                    (username,)
                )
                result = cursor.fetchone()
                if not result:
                    return None
                if isinstance(result, dict):
                    user_id, login, name, stored_hash = (
                        result["id"], result["username"], result["name"], result["password_hash"]
                    )
                else:
                    user_id, login, name, stored_hash = result[0], result[1], result[2], result[3]
                matched, needs_upgrade = verify_password_hash(password, stored_hash)
                if not matched:
                    return None
                if needs_upgrade:
                    cursor.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (hash_password(password), user_id),
                    )
                    conn.commit()
                return {
                    "id": user_id,
                    "auth_provider": "password",
                    "login": login,
                    "name": name or username,
                }
        except Exception as exc:
            raise AuthStorageUnavailable("认证数据库暂时不可用") from exc
    
    def close(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None


# 全局数据库实例
db = Database()
