import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const tokenKey = 'roomink-work.device-token';
const deviceKey = 'roomink-work.device-key';
const pendingLinkKey = 'roomink-work.pending-link';

export type Store = { id: number; name: string; is_receiving?: boolean };
export type Device = { label: string; status: string; stores: Store[] };
export type WorkCall = {
  id: number;
  contact_id: string;
  store_id: number;
  store_name: string;
  from_phone: string;
  customer_name: string | null;
  customer_attention?: { flag: string; ban_type: string; staff_memo: string } | null;
  status: string;
  created_at: string;
};
export type PendingLink = { request_id: string; code: string; claim_secret: string; expires_at: string };

export class WorkApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

const baseUrl = process.env.EXPO_PUBLIC_ROOMINK_API_BASE_URL?.replace(/\/$/, '');

function apiUrl(path: string) {
  if (!baseUrl) throw new Error('接続先が未設定です。EXPO_PUBLIC_ROOMINK_API_BASE_URL を設定してください。');
  return `${baseUrl}${path}`;
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `RoominkWork ${token}` } : {}),
      ...init.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new WorkApiError(
    typeof body.detail === 'string' ? body.detail : '通信に失敗しました。', response.status,
  );
  return body as T;
}

export async function getDeviceKey() {
  const stored = await SecureStore.getItemAsync(deviceKey);
  if (stored) return stored;
  const value = Crypto.randomUUID();
  await SecureStore.setItemAsync(deviceKey, value);
  return value;
}

export async function getToken() { return SecureStore.getItemAsync(tokenKey); }
export async function clearToken() { return SecureStore.deleteItemAsync(tokenKey); }
export async function getPendingLink(): Promise<PendingLink | null> {
  const value = await SecureStore.getItemAsync(pendingLinkKey);
  if (!value) return null;
  try {
    const link = JSON.parse(value) as PendingLink;
    if (Date.parse(link.expires_at) > Date.now()) return link;
  } catch { /* Discard unreadable local state. */ }
  await SecureStore.deleteItemAsync(pendingLinkKey);
  return null;
}
export async function clearPendingLink() { return SecureStore.deleteItemAsync(pendingLinkKey); }

export async function lookupPersonalStores(username: string, password: string) {
  return request<{ stores: Store[] }>('/work/personal-stores/', {
    method: 'POST', body: JSON.stringify({ username, password }),
  });
}

export async function loginPersonal(input: { username: string; password: string; label: string; platform: 'ios' | 'android'; storeIds: number[] }) {
  const device_key = await getDeviceKey();
  const result = await request<{ token: string; device: Device }>('/work/personal-login/', {
    method: 'POST',
    body: JSON.stringify({ ...input, device_key, store_ids: input.storeIds }),
  });
  await SecureStore.setItemAsync(tokenKey, result.token);
  return result.device;
}

export async function createSharedLink(label: string, platform: 'ios' | 'android') {
  const device_key = await getDeviceKey();
  const result = await request<PendingLink>('/work/shared-links/', {
    method: 'POST', body: JSON.stringify({ device_key, label, platform }),
  });
  await SecureStore.setItemAsync(pendingLinkKey, JSON.stringify(result));
  return result;
}

export async function claimSharedLink(requestId: string, claimSecret: string) {
  const result = await request<{ status: string; token?: string; device?: Device }>(`/work/shared-links/${requestId}/claim/`, {
    method: 'POST', body: JSON.stringify({ claim_secret: claimSecret }),
  });
  if (result.token) {
    await SecureStore.setItemAsync(tokenKey, result.token);
    await clearPendingLink();
  }
  return result;
}

export async function rotateToken() {
  const result = await workRequest<{ token: string }>('/work/token/rotate/', {
    method: 'POST', body: '{}',
  });
  await SecureStore.setItemAsync(tokenKey, result.token);
}

export async function workRequest<T>(path: string, init: RequestInit = {}) {
  const token = await getToken();
  if (!token) throw new Error('端末認証がありません。もう一度連携してください。');
  return request<T>(path, init, token);
}
