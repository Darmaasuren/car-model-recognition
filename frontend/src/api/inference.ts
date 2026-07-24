import type { LiveRecognitionResult } from "../models/live";
import {
  buildApiUrl,
  buildWebSocketUrl,
} from "./client";

export interface InferenceResponse {
  results: LiveRecognitionResult[];
}

export type VideoSessionStatus =
  | "pending"
  | "running"
  | "completed"
  | "error"
  | "stopped";

interface VideoSessionResponse {
  sessionId: string;
}

interface VideoRecognitionEvent {
  type: "recognition";
  sessionId: string;
  result: LiveRecognitionResult;
}

interface VideoStatusEvent {
  type: "status";
  sessionId: string;
  status: VideoSessionStatus;
  error?: string | null;
}

type VideoSessionEvent =
  | VideoRecognitionEvent
  | VideoStatusEvent;

export async function recognizeFile(
  file: File,
): Promise<InferenceResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const endpoint = file.type.startsWith("video/")
    ? "/inference/video"
    : "/inference/image";

  const response = await fetch(buildApiUrl(endpoint), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);

    throw new Error(
      error?.detail ?? "Файл танихад алдаа гарлаа.",
    );
  }

  return response.json() as Promise<InferenceResponse>;
}

export async function createVideoSession(
  file: File,
): Promise<VideoSessionResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    buildApiUrl("/inference/video/sessions"),
    {
      method: "POST",
      body: formData,
    },
  );

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      error?.detail ?? "Бичлэг боловсруулахад алдаа гарлаа.",
    );
  }

  return response.json() as Promise<VideoSessionResponse>;
}

export function getVideoSessionStreamUrl(
  sessionId: string,
): string {
  return buildApiUrl(
    `/inference/video/sessions/${encodeURIComponent(sessionId)}/stream`,
  );
}

interface ConnectVideoSessionOptions {
  sessionId: string;
  onRecognition: (result: LiveRecognitionResult) => void;
  onStatus: (
    status: VideoSessionStatus,
    error?: string | null,
  ) => void;
  onError: () => void;
}

export function connectVideoSessionEvents({
  sessionId,
  onRecognition,
  onStatus,
  onError,
}: ConnectVideoSessionOptions): () => void {
  const socket = new WebSocket(
    buildWebSocketUrl(
      `/inference/video/sessions/${encodeURIComponent(sessionId)}/events`,
    ),
  );

  socket.onmessage = (message) => {
    try {
      const event = JSON.parse(
        String(message.data),
      ) as VideoSessionEvent;

      if (event.sessionId !== sessionId) {
        return;
      }

      if (event.type === "recognition") {
        onRecognition(event.result);
      } else {
        onStatus(event.status, event.error);
      }
    } catch {
      onError();
    }
  };

  socket.onerror = onError;

  return () => {
    socket.close();
  };
}

export async function stopVideoSession(
  sessionId: string,
): Promise<void> {
  await fetch(
    buildApiUrl(
      `/inference/video/sessions/${encodeURIComponent(sessionId)}`,
    ),
    { method: "DELETE" },
  );
}
