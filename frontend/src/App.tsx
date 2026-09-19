import { FormEvent, useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

type RouteLeg = {
  mode: string;
  duration_min: number;
  from: string;
  to: string;
  geometry: Array<{ lat: number; lon: number }>;
  line_name?: string;
  line?: string;
};

type RouteResponse = {
  request_id?: string;
  origin: { lat: number; lon: number; label?: string };
  destination: { lat: number; lon: number; label?: string };
  recommended_route: {
    total_duration_min: number;
    legs: RouteLeg[];
    exit_routing?: {
      enabled: boolean;
      fallback_to_station_centroid: boolean;
      explanation?: string;
      fallback_reason?: string;
      origin?: {
        station_id: string;
        station_name: string;
        exit_id: string;
        exit_name: string;
        lat: number;
        lon: number;
      };
      destination?: {
        station_id: string;
        station_name: string;
        exit_id: string;
        exit_name: string;
        lat: number;
        lon: number;
      };
    };
  };
  accessibility: {
    step_free: boolean;
    accessible: boolean;
    verification: string;
    stairs_used: boolean;
    unknown_segments: number;
    lifts_used: Array<{ id: string; station_exit?: string; status: string }>;
    ramps_used: number;
  };
  decision: { reason: string; summary: string; details: string[] };
};

type LocationSuggestion = { address: string; label?: string; lat?: number; lon?: number };

type TrainDisruption = {
  line: string;
  direction?: string;
  stations: string[];
  free_public_bus?: string[];
  free_mrt_shuttle?: string[];
  mrt_shuttle_direction?: string;
};

type TrainServiceStatus = {
  status: number;
  affected_segments: TrainDisruption[];
  messages: string[];
  data_status: string;
};

type RerouteData = {
  status: string;
  previous_route: { remaining_duration_min: number };
  new_route: { remaining_duration_min: number; legs: RouteLeg[] };
  change: { additional_duration_min: number; reason: string | { type: string; message: string } };
};

const API_URL = import.meta.env.VITE_API_URL ?? "";

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
  const [stepFree, setStepFree] = useState(false);
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [error, setError] = useState("");

  // Disruption and reroute states
  const [networkDisruption, setNetworkDisruption] = useState<TrainServiceStatus | null>(null);
  const [routeDisruption, setRouteDisruption] = useState<{
    line: string;
    affected_stations: string[];
    message?: string;
    free_mrt_shuttle?: string[];
    free_public_bus?: string[];
  } | null>(null);
  const [rerouteData, setRerouteData] = useState<RerouteData | null>(null);
  const [activeRouteView, setActiveRouteView] = useState<"rerouted" | "original">("rerouted");

  const originSuggestions = useLocationSuggestions(origin);
  const destinationSuggestions = useLocationSuggestions(destination);

  // Poll global network disruption alerts
  useEffect(() => {
    async function fetchDisruptions() {
      try {
        const res = await fetch(`${API_URL}/api/v1/disruptions/status`);
        if (res.ok) {
          const data = await res.json() as TrainServiceStatus;
          setNetworkDisruption(data);
        }
      } catch {
        // network or server unavailable
      }
    }
    fetchDisruptions();
    const interval = setInterval(fetchDisruptions, 30000);
    return () => clearInterval(interval);
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setRoute(null);
    setRouteDisruption(null);
    setRerouteData(null);
    setActiveRouteView("rerouted");

    try {
      const response = await fetch(`${API_URL}/api/v1/routes/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: { address: origin },
          destination: { address: destination },
          departure_date: departureDate,
          departure_time: departureTime,
          preferences: { stepFree },
        }),
      });
      const result = await response.json() as RouteResponse | { detail?: string };
      if (!response.ok) {
        setError("detail" in result && result.detail ? result.detail : "Unable to plan this route.");
        return;
      }
      const plannedRoute = result as RouteResponse;
      setRoute(plannedRoute);

      // Register active journey and check for disruptions
      const journeyRes = await fetch(`${API_URL}/api/v1/journeys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          route_id: plannedRoute.request_id ?? "route",
          origin: plannedRoute.origin,
          destination: plannedRoute.destination,
          current_position: plannedRoute.origin,
          legs: plannedRoute.recommended_route.legs.map((leg) => ({
            mode: leg.mode,
            line: leg.line_name ?? leg.line,
            from: leg.from,
            to: leg.to,
            duration_min: leg.duration_min,
          })),
        }),
      });

      if (journeyRes.ok) {
        const jData = await journeyRes.json();
        const jId = jData.journey_id;

        const statusRes = await fetch(`${API_URL}/api/v1/journeys/${jId}/status`);
        if (statusRes.ok) {
          const sData = await statusRes.json();
          if (sData.status === "reroute_required" && sData.disruption) {
            setRouteDisruption(sData.disruption);
            // Recalculate remaining journey to avoid the disruption
            const rerouteRes = await fetch(`${API_URL}/api/v1/journeys/${jId}/reroute`, { method: "POST" });
            if (rerouteRes.ok) {
              const rData = await rerouteRes.json() as RerouteData;
              setRerouteData(rData);
              setActiveRouteView("rerouted");
            }
          }
        }
      }
    } catch {
      setError("An unexpected error occurred while planning the route.");
    }
  }

  // Active legs to show (either rerouted or original)
  const currentLegs = (activeRouteView === "rerouted" && rerouteData && rerouteData.new_route.legs.length > 0)
    ? rerouteData.new_route.legs
    : route?.recommended_route.legs ?? [];

  const displayedDuration = (activeRouteView === "rerouted" && rerouteData)
    ? rerouteData.new_route.remaining_duration_min
    : route?.recommended_route.total_duration_min ?? 0;

  const routePoints: [number, number][] = currentLegs.flatMap((leg) =>
    (leg.geometry ?? []).map((point) => [point.lat, point.lon] as [number, number])
  );
  const points: [number, number][] = routePoints.length > 1
    ? routePoints
    : route ? [[route.origin.lat, route.origin.lon], [route.destination.lat, route.destination.lon]] : [[1.3521, 103.8198]];

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
          <label className="preference-toggle"><input type="checkbox" checked={stepFree} onChange={(event) => setStepFree(event.target.checked)} aria-describedby="step-free-description" /><span>Step-free route</span></label>
          <p className="preference-description" id="step-free-description">Avoid stairs. Prefer lifts and ramps.</p>
          <button type="submit">Find route</button>
        </form>

        {route && (
          <section className="route-details">
            <h2>{displayedDuration} min</h2>
            <p className="muted">{route.origin.label ?? "Origin"} to {route.destination.label ?? "Destination"}</p>

            {/* Disruption Alert & Reroute View Controls */}
            {routeDisruption && (
              <div className="route-disruption-alert" role="alert">
                <strong>⚠️ Planned Route Affected by Disruption</strong>
                <p>
                  Your planned route uses the <strong>{routeDisruption.line} Line</strong>, which is currently disrupted across stations (<strong>{routeDisruption.affected_stations.join(", ")}</strong>).
                </p>
                {rerouteData && (
                  <>
                    <p>
                      <span className="reroute-badge">Alternative Route Applied</span>{" "}
                      Takes {rerouteData.new_route.remaining_duration_min} min (
                      {rerouteData.change.additional_duration_min > 0
                        ? `+${rerouteData.change.additional_duration_min} min`
                        : "same duration"}
                      ).
                    </p>
                    <p style={{ fontStyle: "italic", fontSize: "0.82rem", margin: "3px 0 6px" }}>
                      {typeof rerouteData.change.reason === "object"
                        ? rerouteData.change.reason.message
                        : rerouteData.change.reason}
                    </p>
                    <div className="reroute-toggle-group">
                      <button
                        type="button"
                        className={`reroute-toggle-btn ${activeRouteView === "rerouted" ? "active" : ""}`}
                        onClick={() => setActiveRouteView("rerouted")}
                      >
                        ✓ Alternative ({rerouteData.new_route.remaining_duration_min} min)
                      </button>
                      <button
                        type="button"
                        className={`reroute-toggle-btn ${activeRouteView === "original" ? "active" : ""}`}
                        onClick={() => setActiveRouteView("original")}
                      >
                        Original ({route.recommended_route.total_duration_min} min)
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {route.recommended_route.exit_routing && (
              <>
                <p className={route.recommended_route.exit_routing.enabled ? "exit-note" : "exit-note unavailable"}>
                  {route.recommended_route.exit_routing.enabled ? (
                    <>
                      {route.recommended_route.exit_routing.explanation}
                      {route.recommended_route.exit_routing.origin && (
                        <div>
                          <strong>Origin access:</strong> {route.recommended_route.exit_routing.origin.station_name} — {route.recommended_route.exit_routing.origin.exit_name}
                        </div>
                      )}
                      {route.recommended_route.exit_routing.destination && (
                        <div>
                          <strong>Destination access:</strong> {route.recommended_route.exit_routing.destination.station_name} — {route.recommended_route.exit_routing.destination.exit_name}
                        </div>
                      )}
                      {route.recommended_route.exit_routing.fallback_to_station_centroid && (
                        <div style={{ fontSize: "0.8rem", color: "#4b5565", marginTop: 4 }}>
                          {route.recommended_route.exit_routing.fallback_reason === "destination_exit_data_unavailable"
                            ? "ℹ️ Destination exit data unavailable; retaining station centroid access."
                            : route.recommended_route.exit_routing.fallback_reason === "origin_exit_data_unavailable"
                            ? "ℹ️ Origin exit data unavailable; retaining station centroid access."
                            : "ℹ️ Retaining standard station centroid access where exit data was unavailable."}
                        </div>
                      )}
                    </>
                  ) : route.recommended_route.exit_routing.fallback_reason === "no_mrt_segment" ? (
                    "Exit-level routing is unavailable because this journey has no MRT segment."
                  ) : (
                    "No verified MRT exit route was selected; the original station access route is retained."
                  )}
                </p>
                {route.recommended_route.exit_routing.origin && (
                  <details className="station-guide">
                    <summary>Entering {route.recommended_route.exit_routing.origin.station_name}: {route.recommended_route.exit_routing.origin.exit_name}</summary>
                    <p>Enter via <strong>{route.recommended_route.exit_routing.origin.exit_name}</strong> to board the train at <strong>{route.recommended_route.exit_routing.origin.station_name}</strong>.</p>
                    {route.accessibility.step_free && <p>Use signed lifts and ramps where available; avoid stair-only connections.</p>}
                  </details>
                )}
                {route.recommended_route.exit_routing.destination && (
                  <details className="station-guide">
                    <summary>Inside {route.recommended_route.exit_routing.destination.station_name}: {route.recommended_route.exit_routing.destination.exit_name}</summary>
                    <p>After alighting at <strong>{route.recommended_route.exit_routing.destination.station_name}</strong>, follow station signs for <strong>{route.recommended_route.exit_routing.destination.exit_name}</strong>.</p>
                    {route.accessibility.step_free && <p>Use signed lifts and ramps where available; avoid stair-only connections.</p>}
                  </details>
                )}
              </>
            )}

            {route.accessibility.step_free && (
              <div className={route.accessibility.accessible ? "accessibility ok" : "accessibility caution"}>
                <strong>{route.accessibility.accessible ? "✓ Step-free route" : "! No fully verified step-free route found"}</strong>
                <span>{route.decision.summary}</span>
                {route.decision.details.map((detail) => <small key={detail}>{detail}</small>)}
              </div>
            )}

            <ol>
              {currentLegs.map((leg, index) => {
                const lineName = leg.line_name ?? leg.line;
                return (
                  <li key={index}>
                    <strong>{leg.mode === "mrt" ? "MRT" : leg.mode}{lineName ? ` ${lineName}` : ""}</strong>
                    <span>{leg.from} → {leg.to}</span>
                    <small>{leg.duration_min} min</small>
                  </li>
                );
              })}
            </ol>
          </section>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      <section className="map-shell" aria-label="Route map">
        {/* Floating Map Disruption Banner */}
        {networkDisruption && networkDisruption.status === 2 && networkDisruption.affected_segments.length > 0 && (
          <div className="map-disruption-banner" role="alert">
            <span className="banner-icon">⚠️</span>
            <div>
              <strong>Train Service Disruption Active</strong>
              {networkDisruption.affected_segments.map((seg, idx) => (
                <p key={idx}>
                  <strong>{seg.line} Line:</strong> Disrupted stations: {seg.stations.join(", ")}
                  {seg.direction && ` (towards ${seg.direction})`}
                  <br />
                  {seg.free_mrt_shuttle && seg.free_mrt_shuttle.length > 0 && (
                    <span className="mitigation-tag">🚌 Free MRT Shuttle</span>
                  )}
                  {seg.free_public_bus && seg.free_public_bus.length > 0 && (
                    <span className="mitigation-tag">🚍 Free Public Bus</span>
                  )}
                </p>
              ))}
              {networkDisruption.messages && networkDisruption.messages.length > 0 && (
                <p style={{ fontSize: "0.78rem", color: "#7b341e", marginTop: 4 }}>
                  {networkDisruption.messages[0]}
                </p>
              )}
            </div>
          </div>
        )}

        <MapContainer center={points[0]} zoom={12} scrollWheelZoom>
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {route && (
            <>
              <FitRoute points={points} />
              {currentLegs.map((leg, index) => {
                const geometry = (leg.geometry ?? []).map((point) => [point.lat, point.lon] as [number, number]);
                return geometry.length > 1 ? <Polyline key={index} positions={geometry} pathOptions={legStyle(leg.mode, leg.line_name ?? leg.line)} /> : null;
              })}
              {route.recommended_route.exit_routing?.origin && (
                <CircleMarker center={[route.recommended_route.exit_routing.origin.lat, route.recommended_route.exit_routing.origin.lon]} radius={8} pathOptions={{ color: "#172033", fillColor: "#20c997", fillOpacity: 1, weight: 2 }}>
                  <Popup>Origin entrance: {route.recommended_route.exit_routing.origin.exit_name}</Popup>
                </CircleMarker>
              )}
              {route.recommended_route.exit_routing?.destination && (
                <CircleMarker center={[route.recommended_route.exit_routing.destination.lat, route.recommended_route.exit_routing.destination.lon]} radius={8} pathOptions={{ color: "#172033", fillColor: "#f7b731", fillOpacity: 1, weight: 2 }}>
                  <Popup>Selected {route.recommended_route.exit_routing.destination.exit_name}</Popup>
                </CircleMarker>
              )}
              <CircleMarker center={[route.origin.lat, route.origin.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#16803c", fillOpacity: 1, weight: 3 }}>
                <Popup>Origin: {route.origin.label}</Popup>
              </CircleMarker>
              <CircleMarker center={[route.destination.lat, route.destination.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#c43636", fillOpacity: 1, weight: 3 }}>
                <Popup>Destination: {route.destination.label}</Popup>
              </CircleMarker>
            </>
          )}
        </MapContainer>
      </section>
    </main>
  );
}
