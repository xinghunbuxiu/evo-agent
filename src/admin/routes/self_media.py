"""
自媒体运营反馈处理与采集接口。
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request
from fastapi.responses import HTMLResponse


def register_self_media_routes(
    app,
    *,
    workspace,
    task_queue,
    task_priority_normal,
    list_toutiao_accounts: Callable,
    get_toutiao_account_identity: Callable,
    begin_toutiao_account_login: Callable,
    launch_toutiao_account_login: Callable,
    get_toutiao_login_session: Callable,
    list_toutiao_login_sessions: Callable,
    confirm_toutiao_account_login: Callable,
    update_toutiao_account: Callable,
    logout_toutiao_account: Callable,
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    def build_toutiao_handoff_html(*, account_id: str, current: dict, api_base: str, session_id: str | None = None, login_target_url: str | None = None) -> str:
        profile = current.get("profile", {}) if isinstance(current.get("profile"), dict) else {}
        display_name = str(profile.get("display_name") or current.get("display_name") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        profile_url = str(profile.get("profile_url") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        login_status = str(profile.get("login_status") or ("ready" if current.get("logged_in") else "pending"))
        logged_in_text = "yes" if current.get("logged_in") else "no"
        safe_account_id = account_id.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_api_base = api_base.rstrip("/")
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Evo Toutiao Login Handoff</title>
  <style>
    body {{ font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: linear-gradient(135deg, #eff6ff, #f0fdfa); color: #0f172a; }}
    .wrap {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 60px; }}
    .card {{ background: rgba(255,255,255,0.92); border: 1px solid #cbd5e1; border-radius: 20px; padding: 24px; box-shadow: 0 12px 30px rgba(15,23,42,0.06); }}
    .title {{ font-size: 28px; font-weight: 700; margin: 0 0 8px; }}
    .sub {{ font-size: 14px; color: #475569; margin: 0 0 24px; }}
    .grid {{ display: grid; gap: 14px; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .field {{ display: flex; flex-direction: column; gap: 8px; }}
    .full {{ grid-column: 1 / -1; }}
    label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; color: #0f766e; font-weight: 600; }}
    input, textarea {{ border: 1px solid #bfdbfe; border-radius: 12px; padding: 12px 14px; font-size: 14px; background: white; color: #0f172a; }}
    textarea {{ min-height: 84px; resize: vertical; }}
    .status {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }}
    .pill {{ background: #e0f2fe; color: #075985; border-radius: 999px; padding: 8px 12px; font-size: 12px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 22px; }}
    button {{ border: 0; border-radius: 12px; padding: 12px 16px; font-size: 14px; font-weight: 600; cursor: pointer; }}
    .primary {{ background: #0f766e; color: white; }}
    .secondary {{ background: white; color: #0369a1; border: 1px solid #7dd3fc; }}
    .danger {{ background: white; color: #be123c; border: 1px solid #fda4af; }}
    pre {{ margin-top: 20px; background: #0f172a; color: #e2e8f0; border-radius: 14px; padding: 16px; overflow: auto; font-size: 12px; }}
    .msg {{ margin-top: 16px; font-size: 14px; color: #0f766e; }}
    @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1 class="title">Toutiao Login Handoff</h1>
      <p class="sub">这个页面是 evo 的本地登录接管层。现在先支持人工回填登录结果，后面可以替换成真实浏览器或 WebView 自动确认。</p>
      <div class="status">
        <div class="pill" id="pillAccount">account {safe_account_id}</div>
        <div class="pill" id="pillLoggedIn">logged_in {logged_in_text}</div>
        <div class="pill" id="pillLoginStatus">login_status {login_status}</div>
        <div class="pill" id="pillSession">session {str(session_id or profile.get("login_session_id") or "--")}</div>
      </div>
      <div class="grid">
        <div class="field">
          <label>Display Name</label>
          <input id="displayName" value="{display_name}" placeholder="Evo Toutiao" />
        </div>
        <div class="field">
          <label>Profile URL</label>
          <input id="profileUrl" value="{profile_url}" placeholder="https://..." />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea id="notes" placeholder="记录这次接管的登录方式、扫码状态或后续自动化替换计划">{str(profile.get("notes") or "")}</textarea>
        </div>
        <div class="field full">
          <label>Login Target URL</label>
          <input id="loginTargetUrl" value="{str(login_target_url or profile.get("login_target_url") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}" placeholder="https://..." />
        </div>
      </div>
      <div class="actions">
        <button class="secondary" onclick="beginLogin()">重建占位会话</button>
        <button class="secondary" onclick="launchLoginTarget()">发起登录目标</button>
        <button class="secondary" onclick="refreshSnapshots()">手动刷新状态</button>
        <button class="primary" onclick="confirmLogin()">确认已登录</button>
        <button class="secondary" onclick="saveDraft()">保存资料</button>
        <button class="danger" onclick="logoutAccount()">标记登出</button>
      </div>
      <div id="message" class="msg"></div>
      <pre id="output">{current}</pre>
    </div>
  </div>
  <script>
    const accountId = {account_id!r};
    const apiBase = {safe_api_base!r};
    let sessionId = {str(session_id or profile.get("login_session_id") or "")!r};
    function setPill(id, text) {{
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    }}
    async function handle(url, method, body) {{
      const res = await fetch(url, {{
        method,
        headers: {{ 'Content-Type': 'application/json' }},
        credentials: 'include',
        body: body ? JSON.stringify(body) : undefined,
      }});
      const data = await res.json();
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      document.getElementById('message').textContent = data.message || (data.success ? 'ok' : 'failed');
      return data;
    }}
    async function fetchJson(url) {{
      const res = await fetch(url, {{ credentials: 'include' }});
      return await res.json();
    }}
    function payload() {{
      return {{
        display_name: document.getElementById('displayName').value.trim(),
        profile_url: document.getElementById('profileUrl').value.trim(),
        notes: document.getElementById('notes').value.trim(),
        login_target_url: document.getElementById('loginTargetUrl').value.trim(),
      }};
    }}
    async function beginLogin() {{
      const data = await handle(`${{apiBase}}/api/self-media/toutiao/accounts/begin-login`, 'POST', {{
        account_id: accountId,
        display_name: document.getElementById('displayName').value.trim(),
        login_target_url: document.getElementById('loginTargetUrl').value.trim(),
      }});
      sessionId = data?.data?.result?.login_session_id || data?.data?.login_session_id || sessionId;
      await refreshSnapshots();
    }}
    async function launchLoginTarget() {{
      const data = await handle(`${{apiBase}}/api/self-media/toutiao/accounts/${{encodeURIComponent(accountId)}}/launch-login`, 'POST', {{
        session_id: sessionId,
        login_target_url: document.getElementById('loginTargetUrl').value.trim(),
      }});
      const target = data?.data?.result?.login_target_url;
      sessionId = data?.data?.result?.session_id || sessionId;
      if (target) {{
        window.open(target, '_blank', 'noopener,noreferrer');
      }}
      await refreshSnapshots();
    }}
    async function confirmLogin() {{
      await handle(`${{apiBase}}/api/self-media/toutiao/accounts/${{encodeURIComponent(accountId)}}/confirm-login`, 'POST', payload());
      await refreshSnapshots();
    }}
    async function saveDraft() {{
      await handle(`${{apiBase}}/api/self-media/toutiao/accounts/${{encodeURIComponent(accountId)}}`, 'PUT', payload());
      await refreshSnapshots();
    }}
    async function logoutAccount() {{
      await handle(`${{apiBase}}/api/self-media/toutiao/accounts/${{encodeURIComponent(accountId)}}/logout`, 'POST');
      await refreshSnapshots();
    }}
    async function refreshSnapshots() {{
      const accountData = await fetchJson(`${{apiBase}}/api/self-media/toutiao/accounts?account_id=${{encodeURIComponent(accountId)}}`);
      const current = accountData?.data?.current || {{}};
      const profile = current?.profile || {{}};
      sessionId = profile?.login_session_id || sessionId;
      const target = profile?.login_target_url || '';
      const input = document.getElementById('loginTargetUrl');
      if (input && !input.value && target) input.value = target;
      setPill('pillAccount', `account ${{current?.account_id || accountId}}`);
      setPill('pillLoggedIn', `logged_in ${{current?.logged_in ? 'yes' : 'no'}}`);
      setPill('pillLoginStatus', `login_status ${{profile?.login_status || (current?.logged_in ? 'ready' : 'pending')}}`);
      setPill('pillSession', `session ${{sessionId || '--'}}`);
      if (sessionId) {{
        const sessionData = await fetchJson(`${{apiBase}}/api/self-media/toutiao/sessions/${{encodeURIComponent(sessionId)}}`);
        document.getElementById('output').textContent = JSON.stringify({{
          account: accountData?.data || null,
          session: sessionData?.data || null,
        }}, null, 2);
      }} else {{
        document.getElementById('output').textContent = JSON.stringify({{
          account: accountData?.data || null,
          session: null,
        }}, null, 2);
      }}
    }}
    window.setInterval(() => {{
      refreshSnapshots().catch(() => undefined);
    }}, 5000);
    refreshSnapshots().catch(() => undefined);
  </script>
</body>
</html>"""

    @app.get("/api/self-media/toutiao/accounts")
    async def get_toutiao_accounts(account_id: str | None = None):
        listing = list_toutiao_accounts(workspace, {"account_id": account_id or "default"})
        if not listing.get("ok"):
            return error_response(str(listing.get("message") or "账号列表获取失败"), 400)
        current_account_id = str(account_id or "default")
        current = get_toutiao_account_identity(workspace, current_account_id)
        return success_response({
            "account_id": current_account_id,
            "current": current,
            "items": listing.get("items", []),
            "total": listing.get("total", 0),
            "executor": listing.get("executor"),
        })

    @app.get("/api/self-media/toutiao/sessions")
    async def get_toutiao_sessions(account_id: str | None = None):
        result = list_toutiao_login_sessions(workspace, {"account_id": account_id or ""})
        if not result.get("ok"):
            return error_response(str(result.get("message") or "会话列表获取失败"), 400)
        return success_response({
            "account_id": account_id,
            "items": result.get("items", []),
            "total": result.get("total", 0),
            "executor": result.get("executor"),
        })

    @app.get("/api/self-media/toutiao/sessions/{session_id}")
    async def get_toutiao_session(session_id: str):
        result = get_toutiao_login_session(workspace, {"session_id": session_id})
        if not result.get("ok"):
            return error_response(str(result.get("message") or "会话状态获取失败"), 400)
        return success_response({
            "session_id": session_id,
            "session": result.get("result"),
            "executor": result.get("executor"),
        })

    @app.get("/api/self-media/toutiao/accounts/{account_id}/handoff")
    async def get_toutiao_handoff_info(account_id: str, request: Request):
        current = get_toutiao_account_identity(workspace, account_id)
        session_id = str((current.get("profile") or {}).get("login_session_id") or "")
        login_target_url = str((current.get("profile") or {}).get("login_target_url") or "")
        handoff_url = f"{str(request.base_url).rstrip('/')}/self-media/toutiao/handoff/{account_id}"
        return success_response({
            "account_id": account_id,
            "handoff_url": handoff_url,
            "current": current,
            "session_id": session_id or None,
            "login_target_url": login_target_url or None,
        })

    @app.get("/self-media/toutiao/handoff/{account_id}", response_class=HTMLResponse)
    async def open_toutiao_handoff_page(account_id: str, request: Request):
        current = get_toutiao_account_identity(workspace, account_id)
        session_id = str((current.get("profile") or {}).get("login_session_id") or "")
        login_target_url = str((current.get("profile") or {}).get("login_target_url") or "")
        return HTMLResponse(
            build_toutiao_handoff_html(
                account_id=account_id,
                current=current,
                api_base=str(request.base_url).rstrip("/"),
                session_id=session_id or None,
                login_target_url=login_target_url or None,
            )
        )

    @app.post("/api/self-media/toutiao/accounts/begin-login")
    async def begin_toutiao_login(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload.setdefault("account_id", "default")
        result = begin_toutiao_account_login(workspace, payload)
        if not result.get("ok"):
            return error_response(str(result.get("message") or "登录会话创建失败"), 400)
        return success_response(result, result.get("message") or "已创建登录会话")

    @app.post("/api/self-media/toutiao/accounts/{account_id}/launch-login")
    async def launch_toutiao_login(account_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload["account_id"] = account_id
        result = launch_toutiao_account_login(workspace, payload)
        if not result.get("ok"):
            return error_response(str(result.get("message") or "登录目标发起失败"), 400)
        return success_response(result, result.get("message") or "已记录登录目标发起动作")

    @app.put("/api/self-media/toutiao/accounts/{account_id}")
    async def update_toutiao_login_account(account_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload["account_id"] = account_id
        result = update_toutiao_account(workspace, payload)
        if not result.get("ok"):
            return error_response(str(result.get("message") or "账号更新失败"), 400)
        return success_response(result, result.get("message") or "账号信息已更新")

    @app.post("/api/self-media/toutiao/accounts/{account_id}/confirm-login")
    async def confirm_toutiao_login(account_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload["account_id"] = account_id
        result = confirm_toutiao_account_login(workspace, payload)
        if not result.get("ok"):
            return error_response(str(result.get("message") or "登录确认失败"), 400)
        return success_response(result, result.get("message") or "账号已标记为登录就绪")

    @app.post("/api/self-media/toutiao/accounts/{account_id}/logout")
    async def logout_toutiao_login(account_id: str):
        result = logout_toutiao_account(workspace, {"account_id": account_id})
        if not result.get("ok"):
            return error_response(str(result.get("message") or "登出失败"), 400)
        return success_response(result, result.get("message") or "账号已登出")

    @app.post("/api/tenants/{tenant_id}/feedback/process")
    async def process_tenant_feedback(tenant_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload.setdefault("channel", "toutiao")
        feedback_text = str(payload.get("feedback_text") or payload.get("comment_text") or "").strip()
        if not feedback_text:
            return error_response("feedback_text 不能为空", 400)
        task = task_queue.submit(
            task_type="operation_feedback_review",
            payload=payload,
            priority=task_priority_normal,
            tenant_id=tenant_id,
        )
        return success_response({
            "task_id": task.id,
            "tenant_id": tenant_id,
            "channel": payload.get("channel"),
            "status": "submitted",
        }, "反馈处理任务已提交")

    @app.post("/api/tenants/{tenant_id}/feedback/collect")
    async def collect_tenant_feedback(tenant_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        payload.setdefault("channel", "toutiao")
        payload.setdefault("with_replies", True)
        task = task_queue.submit(
            task_type="operation_feedback_collect",
            payload=payload,
            priority=task_priority_normal,
            tenant_id=tenant_id,
        )
        return success_response({
            "task_id": task.id,
            "tenant_id": tenant_id,
            "channel": payload.get("channel"),
            "status": "submitted",
        }, "评论采集任务已提交")
