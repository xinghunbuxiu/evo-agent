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
