import { FormEvent, useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

type RouteResponse = {
  origin: { lat: number; lon: number; label?: string };
  destination: { lat: number; lon: number; label?: string };
  recommended_route: { total_duration_min: number; legs: Array<{ mode: string; duration_min: number; from: string; to: string; geometry: Array<{ lat: number; lon: number }>; line_name?: string }>; exit_routing?: { enabled: boolean; fallback_to_station_centroid: boolean; explanation?: string; fallback_reason?: string; destination?: { station_id: string; station_name: string; exit_id: string; exit_name: string; lat: number; lon: number } } };
  accessibility: { step_free: boolean; accessible: boolean; verification: string; stairs_used: boolean; unknown_segments: number; lifts_used: Array<{ id: string; station_exit?: string; status: string }>; ramps_used: number };
  decision: { reason: string; summary: string; details: string[] };
};
type LocationSuggestion = { address: string };
type CoveredLinkwayFeature = {
  type: string;
  properties: { id?: number; [key: string]: unknown };
  geometry: {
    type: "LineString" | "MultiLineString";
    coordinates: number[][] | number[][][];
  };
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const CARTODB_API_KEY = import.meta.env.VITE_CARTODB_API_KEY;
const TILE_URL = CARTODB_API_KEY
  ? `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${CARTODB_API_KEY}`
  : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

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
  const [showCovered, setShowCovered] = useState(true);
  const [coveredLinkways, setCoveredLinkways] = useState<CoveredLinkwayFeature[]>([]);
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [error, setError] = useState("");
  const originSuggestions = useLocationSuggestions(origin);
  const destinationSuggestions = useLocationSuggestions(destination);

  const routePoints: [number, number][] = route ? route.recommended_route.legs.flatMap((leg) => leg.geometry.map((point) => [point.lat, point.lon] as [number, number])) : [];
  const points: [number, number][] = routePoints.length > 1 ? routePoints : route ? [[route.origin.lat, route.origin.lon], [route.destination.lat, route.destination.lon]] : [[1.3521, 103.8198]];

  useEffect(() => {
    if (!showCovered) {
      setCoveredLinkways([]);
      return;
    }

    let minLat: number;
    let maxLat: number;
    let minLon: number;
    let maxLon: number;

    if (route && routePoints.length > 0) {
      const lats = routePoints.map((p) => p[0]);
      const lons = routePoints.map((p) => p[1]);
      minLat = Math.min(...lats);
      maxLat = Math.max(...lats);
      minLon = Math.min(...lons);
      maxLon = Math.max(...lons);
    } else {
      // Default view bounds around central Singapore (Ang Mo Kio / Bishan corridor)
      minLat = 1.350;
      maxLat = 1.380;
      minLon = 103.835;
      maxLon = 103.865;
    }

    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/geo/covered-linkways?min_lat=${minLat}&max_lat=${maxLat}&min_lon=${minLon}&max_lon=${maxLon}`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: CoveredLinkwayFeature[]) => {
        setCoveredLinkways(data);
      })
      .catch((err) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          setCoveredLinkways([]);
        }
      });

    return () => controller.abort();
  }, [showCovered, route, routePoints.length]);

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
        preferences: { stepFree },
      }),
    });
    const result = await response.json() as RouteResponse | { detail?: string };
    if (!response.ok) {
      setError("detail" in result && result.detail ? result.detail : "Unable to plan this route.");
      return;
    }
    setRoute(result as RouteResponse);
  }

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
          <label className="preference-toggle"><input type="checkbox" checked={showCovered} onChange={(event) => setShowCovered(event.target.checked)} aria-describedby="sheltered-description" /><span>☂️ Sheltered walkways</span></label>
          <p className="preference-description" id="sheltered-description">Highlight LTA covered walkways along walking & wheeling paths.</p>
          <button type="submit">Find route</button>
        </form>
        {route && <section className="route-details"><h2>{route.recommended_route.total_duration_min} min</h2><p className="muted">{route.origin.label ?? "Origin"} to {route.destination.label ?? "Destination"}</p>{showCovered && coveredLinkways.length > 0 && <div className="sheltered-summary"><strong>☂️ {coveredLinkways.length} Sheltered Walkway segments active</strong><small>Continuous covered walkways protect motorized wheelchairs from rain and heat.</small></div>}{route.recommended_route.exit_routing && <><p className={route.recommended_route.exit_routing.enabled ? "exit-note" : "exit-note unavailable"}>{route.recommended_route.exit_routing.enabled ? <>{route.recommended_route.exit_routing.explanation}<br />{route.recommended_route.exit_routing.destination && `Destination access: ${route.recommended_route.exit_routing.destination.station_name} — ${route.recommended_route.exit_routing.destination.exit_name}`}</> : route.recommended_route.exit_routing.fallback_reason === "no_mrt_segment" ? "Exit-level routing is unavailable because this journey has no MRT segment." : "No verified MRT exit route was selected; the original station access route is retained."}</p>{route.recommended_route.exit_routing.destination && <details className="station-guide"><summary>Inside {route.recommended_route.exit_routing.destination.station_name}: {route.recommended_route.exit_routing.destination.exit_name}</summary><p>After alighting at <strong>{route.recommended_route.exit_routing.destination.station_name}</strong>, follow station signs for <strong>{route.recommended_route.exit_routing.destination.exit_name}</strong>.</p>{route.accessibility.step_free && <p>Use signed lifts and ramps where available; avoid stair-only connections.</p>}</details>}</>}{route.accessibility.step_free && <div className={route.accessibility.accessible ? "accessibility ok" : "accessibility caution"}><strong>{route.accessibility.accessible ? "✓ Step-free route" : "! No fully verified step-free route found"}</strong><span>{route.decision.summary}</span>{route.decision.details.map((detail) => <small key={detail}>{detail}</small>)}</div>}<ol>{route.recommended_route.legs.map((leg, index) => <li key={index}><strong>{leg.mode === "mrt" ? "MRT" : leg.mode}{leg.line_name ? ` ${leg.line_name}` : ""}</strong><span>{leg.from} → {leg.to}</span><small>{leg.duration_min} min</small></li>)}</ol></section>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>
      <section className="map-shell" aria-label="Route map">
        <div className="map-floating-panel">
          <label className="map-toggle-item">
            <input type="checkbox" checked={showCovered} onChange={(e) => setShowCovered(e.target.checked)} />
            <span>☂️ Sheltered Walkways</span>
            {showCovered && coveredLinkways.length > 0 && <span className="count-pill">{coveredLinkways.length}</span>}
          </label>
        </div>
        <div className="map-legend">
          <div className="legend-item">
            <span className="legend-line sheltered-line"></span>
            <span>Covered Walkway (LTA)</span>
          </div>
          <div className="legend-item">
            <span className="legend-line walk-line"></span>
            <span>Walking / Wheelchair Leg</span>
          </div>
        </div>
        <MapContainer center={points[0]} zoom={12} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url={TILE_URL}
            maxZoom={19}
          />
          {showCovered && coveredLinkways.map((feature, idx) => {
            const geom = feature.geometry;
            if (geom.type === "LineString") {
              const positions = (geom.coordinates as number[][]).map(([lon, lat]) => [lat, lon] as [number, number]);
              return (
                <Polyline
                  key={`clw-${feature.properties.id ?? idx}`}
                  positions={positions}
                  pathOptions={{ color: "#0099ff", weight: 4, dashArray: "4 6", opacity: 0.9 }}
                >
                  <Popup>
                    <div className="linkway-popup">
                      <strong>☂️ Sheltered Walkway</strong>
                      <p>LTA CoveredLinkWay Network</p>
                      <span className="badge-sheltered">Weather Protected</span>
                    </div>
                  </Popup>
                </Polyline>
              );
            } else if (geom.type === "MultiLineString") {
              const multiPositions = (geom.coordinates as number[][][]).map((line) => line.map(([lon, lat]) => [lat, lon] as [number, number]));
              return (
                <Polyline
                  key={`clw-m-${feature.properties.id ?? idx}`}
                  positions={multiPositions}
                  pathOptions={{ color: "#0099ff", weight: 4, dashArray: "4 6", opacity: 0.9 }}
                >
                  <Popup>
                    <div className="linkway-popup">
                      <strong>☂️ Sheltered Walkway</strong>
                      <p>LTA CoveredLinkWay Network</p>
                      <span className="badge-sheltered">Weather Protected</span>
                    </div>
                  </Popup>
                </Polyline>
              );
            }
            return null;
          })}
          {route && <><FitRoute points={points} />{route.recommended_route.legs.map((leg, index) => { const geometry = leg.geometry.map((point) => [point.lat, point.lon] as [number, number]); return geometry.length > 1 ? <Polyline key={index} positions={geometry} pathOptions={legStyle(leg.mode, leg.line_name)} /> : null; })}{route.recommended_route.exit_routing?.destination && <CircleMarker center={[route.recommended_route.exit_routing.destination.lat, route.recommended_route.exit_routing.destination.lon]} radius={8} pathOptions={{ color: "#172033", fillColor: "#f7b731", fillOpacity: 1, weight: 2 }}><Popup>Selected {route.recommended_route.exit_routing.destination.exit_name}</Popup></CircleMarker>}<CircleMarker center={[route.origin.lat, route.origin.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#16803c", fillOpacity: 1, weight: 3 }}><Popup>Origin: {route.origin.label}</Popup></CircleMarker><CircleMarker center={[route.destination.lat, route.destination.lon]} radius={9} pathOptions={{ color: "#fff", fillColor: "#c43636", fillOpacity: 1, weight: 3 }}><Popup>Destination: {route.destination.label}</Popup></CircleMarker></>}
        </MapContainer>
      </section>
    </main>
  );
}
