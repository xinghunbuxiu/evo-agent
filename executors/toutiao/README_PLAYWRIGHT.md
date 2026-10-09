# 渠道执行器 · Playwright（可选）

默认仍是本地 stub；启用后用真实 Chromium 打开登录页 / 编辑页。

## 安装

```bash
cd evo-os
# 推荐用项目 venv
uv pip install -r requirements-playwright.txt --python .venv/bin/python
.venv/bin/python -m playwright install chromium
# 或：pip install -r requirements-playwright.txt && python -m playwright install chromium
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `EVO_CHANNEL_BROWSER=playwright` | 启用浏览器（默认 `local`） |
| `EVO_CHANNEL_LOGIN_URL` | 登录页 URL |
| `EVO_CHANNEL_EDITOR_URL` | 发文/草稿编辑页 URL（可选） |
| `EVO_CHANNEL_BROWSER_HEADLESS=0` | 有头模式，便于扫码登录 |
| `EVO_CHANNEL_LOGIN_HOLD_MS=15000` | 有头登录等待毫秒 |

兼容旧名：`EVO_TOUTIAO_BROWSER` / `EVO_TOUTIAO_LOGIN_TARGET_URL`。

## 冒烟

```bash
export EVO_CHANNEL_BROWSER=playwright
export EVO_CHANNEL_LOGIN_URL=https://example.com
export EVO_CHANNEL_BROWSER_HEADLESS=1
python3 executors/toutiao/scripts/cli.py account launch-login --account default --login-target-url https://example.com
python3 executors/toutiao/scripts/cli.py account status --account default
```

会话状态落在 `executors/toutiao/data/browser/states/`。
