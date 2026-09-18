import { FormEvent, useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

type RouteResponse = {
  origin: { lat: number; lon: number; label?: string };
  destination: { lat: number; lon: number; label?: string };
  recommended_route: { total_duration_min: number; legs: Array<{ mode: string; duration_min: number; from: string; to: string; geometry: Array<{ lat: number; lon: number }>; line_name?: string }> };
};
type LocationSuggestion = { address: string };

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function useLocationSuggestions(query: string) {
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  useEffect(() => {
    if (query.trim().length < 2) { setSuggestions([]); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/locations/search?query=${encodeURIComponent(query)}`, { signal: controller.signal });
        setSuggestions(response.ok ? await response.json() : []);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) setSuggestions([]);
      }
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query]);
  return suggestions;
}

function FitRoute({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => { map.fitBounds(points, { padding: [48, 48] }); }, [map, points]);
  return null;
}

function legStyle(mode: string, lineName?: string) {
  if (mode === "walk") return { color: "#687386", weight: 4, dashArray: "3 10" };
  if (mode === "bus") return { color: "#1b9b54", weight: 5 };
  const line = (lineName ?? "").toUpperCase();
  const mrtColors: Record<string, string> = { NS: "#d42d2d", EW: "#159947", NE: "#8c3fa8", CC: "#f09b27", DT: "#2469b1", TE: "#9a5a33", BP: "#76808e", CG: "#159947" };
  const prefix = Object.keys(mrtColors).find((code) => line.startsWith(code));
  return { color: prefix ? mrtColors[prefix] : "#2469b1", weight: 6 };
}

export default function App() {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departureDate, setDepartureDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [departureTime, setDepartureTime] = useState(() => new Date().toTimeString().slice(0, 5));
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [error, setError] = useState("");
  const originSuggestions = useLocationSuggestions(origin);
  const destinationSuggestions = useLocationSuggestions(destination);

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
    setRoute(result as RouteResponse);
  }

  const routePoints: [number, number][] = route ? route.recommended_route.legs.flatMap((leg) => leg.geometry.map((point) => [point.lat, point.lon] as [number, number])) : [];
  const points: [number, number][] = routePoints.length > 1 ? routePoints : route ? [[route.origin.lat, route.origin.lon], [route.destination.lat, route.destination.lon]] : [[1.3521, 103.8198]];

  return (
    <main>
      <section className="panel">
        <h1>Route planner</h1>
        <form onSubmit={handleSubmit}>
          <input aria-label="Origin" placeholder="Origin" list="origin-suggestions" value={origin} onChange={(event) => setOrigin(event.target.value)} required />
          <datalist id="origin-suggestions">{originSuggestions.map((location) => <option key={location.address} value={location.address} />)}</datalist>
          <input aria-label="Destination" placeholder="Destination" list="destination-suggestions" value={destination} onChange={(event) => setDestination(event.target.value)} required />
          <datalist id="destination-suggestions">{destinationSuggestions.map((location) => <option key={location.address} value={location.address} />)}</datalist>
          <div className="date-time"><input aria-label="Departure date" type="date" value={departureDate} onChange={(event) => setDepartureDate(event.target.value)} required /><input aria-label="Departure time" type="time" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} required /></div>
          <button type="submit">Find route</button>
        </form>
        {route && <section className="route-details"><h2>{route.recommended_route.total_duration_min} min</h2><p className="muted">{route.origin.label ?? "Origin"} to {route.destination.label ?? "Destination"}</p><ol>{route.recommended_route.legs.map((leg, index) => <li key={index}><strong>{leg.mode === "mrt" ? "MRT" : leg.mode}{leg.line_name ? ` ${leg.line_name}` : ""}</strong><span>{leg.from} → {leg.to}</span><small>{leg.duration_min} min</small></li>)}</ol></section>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>
      <section className="map-shell" aria-label="Route map">
        <MapContainer center={points[0]} zoom={12} scrollWheelZoom>
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {route && <><FitRoute points={points} />{route.recommended_route.legs.map((leg, index) => { const geometry = leg.geometry.map((point) => [point.lat, point.lon] as [number, number]); return geometry.length > 1 ? <Polyline key={index} positions={geometry} pathOptions={legStyle(leg.mode, leg.line_name)} /> : null; })}<CircleMarker center={[route.origin.lat, route.origin.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#16803c", fillOpacity: 1, weight: 3 }}><Popup>Origin: {route.origin.label}</Popup></CircleMarker><CircleMarker center={[route.destination.lat, route.destination.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#c43636", fillOpacity: 1, weight: 3 }}><Popup>Destination: {route.destination.label}</Popup></CircleMarker></>}
        </MapContainer>
      </section>
    </main>
  );
}
