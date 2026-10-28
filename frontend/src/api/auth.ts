import { apiFetch, buildApiUrl } from './client';

export interface User { id: number; username: string; role: string }

export async function getMe(): Promise<User | null> {
  const response = await apiFetch(buildApiUrl('/auth/me'));
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Сервер эсвэл database ажиллахгүй байна.');
  return response.json();
}

export async function login(username: string, password: string): Promise<User> {
  const bytes = new TextEncoder().encode(`${username}:${password}`);
  const credentials = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''));
  const response = await apiFetch(buildApiUrl('/auth/login'), {
    method: 'POST', headers: { Authorization: `Basic ${credentials}` },
  });
  if (!response.ok) {
    throw new Error(response.status === 429 ? 'Олон удаа оролдлоо. Түр хүлээнэ үү.' :
      response.status === 401 ? 'Username эсвэл password буруу байна.' :
      response.status === 503 ? 'Database холболт эсвэл хүснэгтийн алдаа. Backend log шалгана уу.' :
      'Нэвтрэхэд алдаа гарлаа.');
  }
  return response.json();
}

export async function logout(): Promise<void> {
  const response = await apiFetch(buildApiUrl('/auth/logout'), { method: 'POST' });
  if (!response.ok) throw new Error('Гарахад алдаа гарлаа. Дахин оролдоно уу.');
}
