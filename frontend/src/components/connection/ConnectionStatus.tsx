import type { ConnectionState } from "../../models/live";
import "./ConnectionStatus.css";

interface ConnectionStatusProps {
  status: ConnectionState;
}

const labels: Record<ConnectionState, string> = {
  connecting: "Холбогдож байна",
  connected: "Холбогдсон",
  disconnected: "Холболт тасарсан",
  error: "Холболтын алдаа",
};

export function ConnectionStatus({
  status,
}: ConnectionStatusProps) {
  return (
    <div
      className={`connection-status connection-status--${status}`}
      role="status"
    >
      <span className="connection-status__dot" />
      <span>{labels[status]}</span>
    </div>
  );
}