export type ConnectionState =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export interface Prediction {
  label: string;
  confidence: number;
}

export interface LiveRecognitionResult {
  eventId: string;
  trackId?: number;
  detectedAt: string;
  cropUrl: string;

  model?: Prediction;
  color?: Prediction;
  vehicleType?: Prediction;
  view?: Prediction;
  seatbelt?: SeatbeltResult | null;
}

export interface RecognitionEvent {
  type: "recognition";
  cameraId: string;
  result: LiveRecognitionResult;
}

export interface SeatbeltResult {
  status: "completed" | "unknown" | "skipped" | "error";
  reason: string;
  detections: {
    className: string;
    confidence: number;
    bbox: [number, number, number, number];
  }[];
  image?: { width: number; height: number } | null;
}
