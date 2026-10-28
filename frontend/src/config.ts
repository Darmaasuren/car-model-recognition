function requireEnvironmentVariable(
  name: string,
  value: string | undefined,
): string {
  const normalizedValue = value?.trim();

  if (!normalizedValue) {
    throw new Error(
      `${name} environment variable тохируулаагүй байна.`,
    );
  }

  return normalizedValue.replace(/\/+$/, "");
}

// Development requests use Vite's origin so browser session cookies stay first-party.
function browserApiUrl(value: string): string {
  if (!import.meta.env.DEV) return value;
  const url = new URL(value);
  return `${window.location.origin}${url.pathname}`;
}

function browserWebSocketUrl(value: string): string {
  if (!import.meta.env.DEV) return value;
  const url = new URL(value);
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${url.pathname}`;
}

export const environment = Object.freeze({
  apiBaseUrl: browserApiUrl(requireEnvironmentVariable(
    "VITE_API_BASE_URL",
    import.meta.env.VITE_API_BASE_URL,
  )),
  webSocketBaseUrl: browserWebSocketUrl(requireEnvironmentVariable(
    "VITE_WS_BASE_URL",
    import.meta.env.VITE_WS_BASE_URL,
  )),
  cameraId: requireEnvironmentVariable(
    "VITE_CAMERA_ID",
    import.meta.env.VITE_CAMERA_ID,
  ),
});
