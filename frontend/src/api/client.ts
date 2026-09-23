import { environment } from "../config";

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export function buildApiUrl(path: string): string {
  return `${environment.apiBaseUrl}${normalizePath(path)}`;
}

export function buildWebSocketUrl(path: string): string {
  return `${environment.webSocketBaseUrl}${normalizePath(path)}`;
}

export function resolveMediaUrl(path: string): string {
  if (
    path.startsWith("http://") ||
    path.startsWith("https://") ||
    path.startsWith("blob:")
  ) {
    return path;
  }

  const backendOrigin = new URL(environment.apiBaseUrl).origin;

  return `${backendOrigin}${normalizePath(path)}`;
}

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, { ...options, credentials: 'include' });
  if (response.status === 401 && !url.endsWith('/auth/login')) {
    window.dispatchEvent(new Event('auth-expired'));
  }
  return response;
}
