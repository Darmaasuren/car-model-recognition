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
}

export interface RecognitionEvent {
  type: "recognition";
  cameraId: string;
  result: LiveRecognitionResult;
}
