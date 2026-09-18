import { FormEvent, useState } from "react";

type RouteResponse = {
  recommended_route: { total_duration_min: number; legs: Array<{ mode: string; duration_min: number; from: string; to: string }> };
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departureDate, setDepartureDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [departureTime, setDepartureTime] = useState(() => new Date().toTimeString().slice(0, 5));
  const [route, setRoute] = useState<RouteResponse["recommended_route"] | null>(null);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setRoute(null);

    const response = await fetch(`${API_URL}/api/v1/routes/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: { address: origin },
        destination: { address: destination },
        departure_date: departureDate,
        departure_time: departureTime,
      }),
    });
    const result = await response.json() as RouteResponse | { detail?: string };
    if (!response.ok) {
      setError("detail" in result && result.detail ? result.detail : "Unable to plan this route.");
      return;
    }
    setRoute((result as RouteResponse).recommended_route);
  }

  return (
    <>
      <form onSubmit={handleSubmit}>
        <input
          aria-label="Origin"
          placeholder="Origin"
          value={origin}
          onChange={(event) => setOrigin(event.target.value)}
        />
        <input
          aria-label="Destination"
          placeholder="Destination"
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
        />
        <input
          aria-label="Departure date"
          type="date"
          value={departureDate}
          onChange={(event) => setDepartureDate(event.target.value)}
        />
        <input
          aria-label="Departure time"
          type="time"
          value={departureTime}
          onChange={(event) => setDepartureTime(event.target.value)}
        />
        <button type="submit">Enter</button>
      </form>
      {route && <div><p>{route.total_duration_min} min</p>{route.legs.map((leg, index) => <p key={index}>{leg.mode}: {leg.from} to {leg.to} ({leg.duration_min} min)</p>)}</div>}
      {error && <p role="alert">{error}</p>}
    </>
  );
}
