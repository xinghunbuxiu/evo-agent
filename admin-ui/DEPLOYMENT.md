# Admin UI 部署与公开预览

## Cloudflare Pages（推荐）

当前 Admin UI 是 Vue 3 + Vite 静态前端，构建产物位于 `admin-ui/dist`。可以用 Cloudflare Pages 托管，不需要先部署 Admin API 就能查看公开演示页。

首次创建 Pages 项目时使用以下设置：

| 设置 | 值 |
| --- | --- |
| Git provider | GitHub |
| Repository | `xinghunbuxiu/evo-agent` |
| Production branch | `main` |
| Root directory | `admin-ui` |
| Build command | `npm run build` |
| Build output directory | `dist` |

建议启用 Pull request preview deployments。PR 更新后，Cloudflare 会为该 PR 构建预览部署；访问部署域名时请使用：

```text
https://<pages-project>.pages.dev/preview
```

不要把 `EVO_ADMIN_API_BASE` 配成公开预览所必需的环境变量。该变量只用于 Vite 开发服务器的 `/api` 与 `/auth` 代理；公开预览页使用本地样例数据，不依赖 Admin API。

## 预览页边界

- `/preview` 是公开、只读的产品展示页面。
- 页面中的 Mission、任务、Worker、知识资产均为演示样例，不代表线上真实状态。
- 预览页路由在认证守卫之前放行，不调用用户会话检查，也不清理或写入访客的登录状态。
- 预览页不触发 Worker、Broker、Validator、Artifact Store 或其他业务写操作。
- 正式业务路由仍走原有认证流程；不要为了让演示页可访问而把整个 Admin UI 改成公开访问。
- 不要在预览页面或静态构建变量中放置 API 密钥、私钥、签名密钥或其他服务端凭据。

## SPA 路由

`admin-ui/public/_redirects` 中的规则：

```text
/* /index.html 200
```

用于 Cloudflare Pages 将前端路由请求回退到 Vue 应用入口。部署后应分别检查 `/preview` 和正式登录路由是否可正常加载。

## 本地验证

在 `admin-ui/` 目录执行：

```bash
npm ci
npm run build
npm run preview
```

本地预览服务启动后，打开终端显示的地址并访问 `/preview`。

## 首次连接仍需项目所有者完成

仓库与 Cloudflare Pages 的 GitHub 授权、项目创建及首次部署必须由拥有 Cloudflare/GitHub 账号权限的人在 Cloudflare 控制台确认。本仓库代码不会保存 Cloudflare API Token，也不会代替账号所有者完成授权。
