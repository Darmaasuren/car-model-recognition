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

export const environment = Object.freeze({
  apiBaseUrl: requireEnvironmentVariable(
    "VITE_API_BASE_URL",
    import.meta.env.VITE_API_BASE_URL,
  ),
  webSocketBaseUrl: requireEnvironmentVariable(
    "VITE_WS_BASE_URL",
    import.meta.env.VITE_WS_BASE_URL,
  ),
  cameraId: requireEnvironmentVariable(
    "VITE_CAMERA_ID",
    import.meta.env.VITE_CAMERA_ID,
  ),
});
