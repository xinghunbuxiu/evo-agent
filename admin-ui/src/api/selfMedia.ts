import { get, post, put } from './request'

export interface ToutiaoAccountProfile {
  account_id?: string
  display_name?: string | null
  logged_in?: boolean
  profile?: Record<string, unknown>
  executor?: {
    name?: string
    adapter?: string
    root_dir?: string
  }
}

export interface ToutiaoAccountsPayload {
  account_id?: string
  current?: ToutiaoAccountProfile
  items?: Array<Record<string, unknown>>
  total?: number
  executor?: {
    name?: string
    adapter?: string
    root_dir?: string
  }
}

export interface ToutiaoHandoffPayload {
  account_id?: string
  handoff_url?: string
  current?: ToutiaoAccountProfile
  session_id?: string | null
  login_target_url?: string | null
}

export interface ToutiaoLoginSession {
  session_id?: string
  account_id?: string
  status?: string
  display_name?: string
  profile_url?: string
  created_at?: string
  updated_at?: string
  notes?: string
  events?: Array<{
    at?: string
    type?: string
    detail?: string
  }>
}

export interface ToutiaoSessionsPayload {
  account_id?: string
  items?: ToutiaoLoginSession[]
  total?: number
}

export function getToutiaoAccounts(accountId = 'default') {
  return get<ToutiaoAccountsPayload>(`/api/self-media/toutiao/accounts?account_id=${encodeURIComponent(accountId)}`)
}

export function beginToutiaoLogin(payload: {
  account_id: string
  display_name?: string
  login_target_url?: string
}) {
  return post('/api/self-media/toutiao/accounts/begin-login', payload)
}

export function updateToutiaoAccount(
  accountId: string,
  payload: {
    display_name?: string
    profile_url?: string
    login_target_url?: string
    notes?: string
    login_status?: string
    logged_in?: boolean
  },
) {
  return put(`/api/self-media/toutiao/accounts/${encodeURIComponent(accountId)}`, payload)
}

export function confirmToutiaoLogin(
  accountId: string,
  payload: {
    display_name?: string
    profile_url?: string
  },
) {
  return post(`/api/self-media/toutiao/accounts/${encodeURIComponent(accountId)}/confirm-login`, payload)
}

export function logoutToutiaoLogin(accountId: string) {
  return post(`/api/self-media/toutiao/accounts/${encodeURIComponent(accountId)}/logout`, {})
}

export function getToutiaoHandoffInfo(accountId: string) {
  return get<ToutiaoHandoffPayload>(`/api/self-media/toutiao/accounts/${encodeURIComponent(accountId)}/handoff`)
}

export function getToutiaoSessions(accountId = '') {
  const suffix = accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''
  return get<ToutiaoSessionsPayload>(`/api/self-media/toutiao/sessions${suffix}`)
}

export function launchToutiaoLogin(
  accountId: string,
  payload: {
    session_id?: string
    login_target_url?: string
  },
) {
  return post(`/api/self-media/toutiao/accounts/${encodeURIComponent(accountId)}/launch-login`, payload)
}
