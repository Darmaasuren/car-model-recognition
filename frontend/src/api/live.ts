import type { RecognitionEvent } from "../models/live";
import {
  buildApiUrl,
  buildWebSocketUrl,
} from "./client";

export function getLiveStreamUrl(cameraId: string): string {
  const encodedCameraId = encodeURIComponent(cameraId);

  return buildApiUrl(
    `/live/cameras/${encodedCameraId}/stream`,
  );
}

interface ConnectLiveEventsOptions {
  cameraId: string;
  onConnected: () => void;
  onDisconnected: () => void;
  onError: () => void;
  onRecognition: (event: RecognitionEvent) => void;
}

export function connectLiveEvents({
  cameraId,
  onConnected,
  onDisconnected,
  onError,
  onRecognition,
}: ConnectLiveEventsOptions): () => void {
  const encodedCameraId = encodeURIComponent(cameraId);

  const socket = new WebSocket(
    buildWebSocketUrl(
      `/live/cameras/${encodedCameraId}/events`,
    ),
  );

  socket.onopen = () => {
    onConnected();
  };

  socket.onmessage = (message) => {
    try {
      const event = JSON.parse(
        String(message.data),
      ) as RecognitionEvent;

      if (
        event.type === "recognition" &&
        event.cameraId === cameraId
      ) {
        onRecognition(event);
      }
    } catch {
      console.error(
        "WebSocket-оос зөв бус JSON мэдээлэл ирлээ.",
      );
    }
  };

  socket.onerror = () => {
    onError();
  };

  socket.onclose = (event) => {
    if (event.code === 4401) window.dispatchEvent(new Event("auth-expired"));
    onDisconnected();
  };

  return () => {
    socket.close();
  };
}