// 认证相关 API
import { get, post } from './request'

export interface UserProfile {
  id: number
  login: string
  name: string
  token?: string
  gitee_login?: string
}

// 账号密码登录
export function login(username: string, password: string) {
  return post<UserProfile>('/api/login', { username, password })
}

// 注册
export function register(username: string, password: string) {
  return post('/api/register', { username, password })
}

// 登出
export function logout() {
  return post('/api/logout', {})
}

// 获取当前用户信息
export function getUser() {
  return get<UserProfile>('/api/user')
}

// 绑定 Gitee Token
export function bindGiteeToken(token: string) {
  return post('/api/user/gitee-token', { token })
}
