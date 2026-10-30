# Evo Admin 部署指南

全自动、无需人工干预的 Evo 后台管理系统。

## 功能特性

- ✅ **任务队列** - 异步处理多项目分析
- ✅ **状态追踪** - 实时查看任务进度
- ✅ **Gitee OAuth** - 安全登录
- ✅ **知识库管理** - 浏览云端技能
- ✅ **多租户支持** - 项目隔离
- ✅ **Docker 部署** - 一键启动

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 Gitee OAuth 配置
```

### 2. 启动服务

```bash
docker-compose up -d
```

### 3. 访问管理界面

打开 http://localhost:8000

点击 "使用 Gitee 账号登录"

## 配置说明

### Gitee OAuth 设置

1. 访问 https://gitee.com/oauth/applications
2. 创建新应用
3. 回调地址填: `http://localhost:8000/auth/callback`
4. 将 Client ID 和 Secret 填入 `.env`

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `GITEE_CLIENT_ID` | ✅ | Gitee OAuth Client ID |
| `GITEE_CLIENT_SECRET` | ✅ | Gitee OAuth Secret |
| `GITEE_REDIRECT_URI` | ✅ | 回调地址 |
| `SESSION_SECRET` | ⚠️ | Session 密钥（生产环境必须更换） |
| `GITEE_TOKEN` | ✅ | Gitee API Token |

## 使用流程

### 1. 创建分析任务

1. 登录后进入 "任务队列"
2. 点击 "新建任务"
3. 选择任务类型（分析/重构/同步）
4. 输入代码路径
5. 提交后自动执行

### 2. 查看进度

- 仪表盘显示实时统计
- 任务列表显示进度条
- 详情页显示完整结果

### 3. 管理知识库

- 浏览云端技能
- 查看技能详情
- 同步本地技能到云端

## 架构说明

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  用户浏览器  │────▶│  Evo Admin  │────▶│  任务队列    │
│             │     │  (FastAPI)  │     │             │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                            │                    │
                            ▼                    ▼
                      ┌─────────────┐     ┌─────────────┐
                      │  Gitee OAuth│     │  Evo Worker │
                      │             │     │ (后台执行) │
                      └─────────────┘     └──────┬──────┘
                                                  │
                                                  ▼
                                            ┌─────────────┐
                                            │  分析/重构   │
                                            │  经验记录    │
                                            │  技能生成    │
                                            └─────────────┘
```

## API 接口

### 任务管理

```bash
# 创建任务
POST /api/tasks
{
  "type": "analyze",
  "payload": {"path": "/workspace/input/app.js"},
  "priority": 2
}

# 获取任务
GET /api/tasks/{task_id}

# 取消任务
DELETE /api/tasks/{task_id}
```

### 知识库

```bash
# 列出云端技能
GET /api/knowledge/skills

# 获取技能详情
GET /api/knowledge/skills/{domain}/{skill_name}
```

### 统计信息

```bash
GET /api/stats
```

### Mission Worker Claim 恢复复核

服务启动时，如果关联队列任务缺失、状态无法读取、仍未结束，或 Worker 释放失败，系统会保留占用并标记为 `needs_review`，避免误释放正在使用的员工。

```bash
# 使用已登录浏览器会话对应的 session Cookie，并明确指定租户
curl -b "session=<登录后获得的 session cookie>" \
  "http://localhost:8000/api/missions/worker-claims/recovery-review?tenant_id=tenant-a&limit=100"
```

接口只读取已持久化的 Mission 记录，不刷新 Mission、不派发任务，也不会释放 Worker。当前它提供的是**待复核清单**，不是人工确认/释放操作接口。

该接口要求有效登录，并且必须指定已授权的 `tenant_id`。租户成员关系目前通过部署环境变量显式配置，不提供用户自助加入或 HTTP 提权入口；未配置、配置错误或身份字段不完整时一律拒绝访问。账号密码用户与 Gitee 用户使用不同的身份命名空间，避免相同数字 ID 冲突。

```bash
# 示例：为 password 登录用户 ID=7 授予 tenant-a 管理员角色，
# 为 Gitee 用户 ID=12345 授予 tenant-a 只读成员角色
EVO_TENANT_MEMBERSHIPS_JSON='{"password:7":{"tenant-a":"tenant_admin"},"gitee:12345":{"tenant-a":"viewer"}}'
```

角色目前仅用于访问边界识别：`tenant_admin`、`member`、`viewer` 均可读取自己所属租户的复核清单；尚未开放人工释放写操作。配置变更应通过受控部署配置完成，禁止将该环境变量暴露给普通用户。处理前仍需核对任务队列与 Worker 注册表中的实际状态。

## 生产部署

### 1. 安全加固

```bash
# 生成强密钥
openssl rand -base64 32

# 填入 .env
SESSION_SECRET=your-strong-secret-key
```

### 2. 使用 Nginx 反向代理

```yaml
# docker-compose.yml 取消注释 nginx 服务
```

### 3. 启用 HTTPS

```bash
# 使用 Let's Encrypt
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 4. 监控

```bash
# 查看日志
docker-compose logs -f evo-admin

# 健康检查
curl http://localhost:8000/health
```

## 故障排除

### 登录失败

- 检查 `GITEE_CLIENT_ID` 和 `GITEE_CLIENT_SECRET`
- 确认回调地址配置正确

### 任务不执行

- 检查 `evo-worker` 服务是否运行
- 查看日志: `docker-compose logs evo-worker`

### 无法访问 Gitee

- 检查网络连接
- 验证 `GITEE_TOKEN` 是否有效

## 开发模式

```bash
# 本地运行（不启用 Docker）
cd src
pip install fastapi uvicorn starlette jinja2 httpx
python3 -m uvicorn admin.server:create_app --reload --port 8000 --factory
```

## 路线图

- [ ] Redis 分布式队列
- [ ] WebSocket 实时推送
- [ ] 多 Worker 横向扩展
- [ ] 任务调度（定时分析）
- [ ] 技能市场（分享/下载）
