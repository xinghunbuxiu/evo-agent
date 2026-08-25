"""
认证、当前用户与基础状态接口。
"""

from __future__ import annotations

from typing import Callable

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


def register_auth_routes(
    app,
    *,
    db,
    mysql_available: bool,
    task_queue,
    sessions: dict,
    create_session_response: Callable[[dict, str], JSONResponse],
    get_session_user: Callable[[Request], dict | None],
    delete_session: Callable[[str | None], None],
    persist_sessions: Callable[[], None],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    @app.post("/api/login")
    async def login(request: Request):
        data = await request.json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return error_response("用户名和密码不能为空", 400)

        user = db.verify_password(username, password)
        if not user:
            return error_response("用户名或密码错误", 401)

        return create_session_response(user)

    @app.post("/api/register")
    async def register(request: Request):
        data = await request.json()
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return error_response("用户名和密码不能为空", 400)

        if len(password) < 6:
            return error_response("密码至少需要6位", 400)

        success = db.create_user(username, password)
        if not success:
            return error_response("用户名已存在", 400)

        return success_response(None, "注册成功")

    @app.post("/api/login/gitee")
    async def login_gitee(request: Request):
        data = await request.json()
        token = data.get("token")

        if not token:
            raise HTTPException(400, "Token 不能为空")

        user = await db.verify_gitee_token(token)
        if not user:
            raise HTTPException(401, "无效的 Token")

        return create_session_response(user)

    @app.get("/api/db/status")
    async def db_status():
        try:
            if not mysql_available:
                return error_response("pymysql 未安装", 500)

            db.init_tables()
            return success_response({"mysql_host": db.host, "mysql_available": True})
        except Exception as exc:
            return error_response(str(exc), 500)

    @app.post("/api/logout")
    async def logout(request: Request):
        delete_session(request.cookies.get("session"))

        response = JSONResponse(success_response(None, "登出成功"))
        response.delete_cookie("session")
        return response

    @app.get("/api/user")
    async def get_user(request: Request):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)

        return success_response(user)

    @app.post("/api/user/gitee-token")
    async def bind_gitee_token(request: Request):
        session_id = request.cookies.get("session")
        user = get_session_user(request)
        if not session_id or not user:
            return error_response("未登录", 401)

        data = await request.json()
        token = data.get("token")

        if not token:
            return error_response("Token 不能为空", 400)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://gitee.com/api/v5/user",
                headers={"Authorization": f"token {token}"},
            )
            if resp.status_code != 200:
                return error_response("无效的 Gitee Token", 400)

            gitee_user = resp.json()

        sessions[session_id]["token"] = token
        sessions[session_id]["gitee_login"] = gitee_user.get("login")
        persist_sessions()

        return success_response({
            "gitee_login": gitee_user.get("login"),
            "gitee_name": gitee_user.get("name"),
        }, "Gitee Token 绑定成功")

    @app.delete("/api/user/gitee-token")
    async def unbind_gitee_token(request: Request):
        session_id = request.cookies.get("session")
        user = get_session_user(request)
        if not session_id or not user:
            return error_response("未登录", 401)

        user.pop("token", None)
        user.pop("gitee_login", None)
        persist_sessions()

        return success_response(None, "已解绑 Gitee Token")

    @app.get("/api/stats")
    async def get_stats():
        all_tasks = task_queue.list_tasks(limit=1000)
        return {
            "tasks": {
                "total": len(all_tasks),
                "pending": len([t for t in all_tasks if t.status.value == "pending"]),
                "running": len([t for t in all_tasks if t.status.value == "running"]),
                "success": len([t for t in all_tasks if t.status.value == "success"]),
                "failed": len([t for t in all_tasks if t.status.value == "failed"]),
            }
        }
