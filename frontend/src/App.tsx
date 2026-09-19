import { FormEvent, Fragment, useEffect, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

type ExitCandidate = {
  id: string;
  station_id: string;
  station_name: string;
  exit_id: string;
  exit_name: string;
  lat: number;
  lon: number;
  // LTA reports lift outages only; no outage is not proof an exit has a lift.
  lift_status: "no_reported_outage" | "maintenance" | string;
  lift_alerts: string[];
  station_lift_alerts: string[];
  is_selected: boolean;
};

type RouteResponse = {
  origin: { lat: number; lon: number; label?: string };
  destination: { lat: number; lon: number; label?: string };
  recommended_route: {
    total_duration_min: number;
    legs: Array<{
      mode: string;
      duration_min: number;
      from: string;
      to: string;
      geometry: Array<{ lat: number; lon: number }>;
      line_name?: string;
      accessibility?: string;
    }>;
    exit_routing?: {
      enabled: boolean;
      fallback_to_station_centroid: boolean;
      explanation?: string;
      fallback_reason?: string;
      origin?: { station_id: string; station_name: string; exit_id: string; exit_name: string; lat: number; lon: number };
      destination?: { station_id: string; station_name: string; exit_id: string; exit_name: string; lat: number; lon: number };
      candidate_exits?: ExitCandidate[];
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
    unavailable_facilities: number;
    station_exits_considered: string[];
  };
  decision: { reason: string; summary: string; details: string[] };
  rain_forecast?: {
    rain_along_route: boolean;
    rain_severity: string;
    currently_raining: boolean;
    current_rainfall_mm: number;
    point_forecasts: Array<{
      lat: number; lon: number; rain_expected: boolean;
      rain_severity: string; forecast_area: string;
      forecast_text: string; valid_period: string;
    }>;
    recommendation: string;
  } | null;
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

type StationGroundFeature = {
  type: string;
  properties: {
    OBJECTID?: number;
    NAME?: string;
    GRND_LEVEL?: "UNDERGROUND" | "ABOVEGROUND" | string;
    TYPE?: string;
    [key: string]: unknown;
  };
  geometry: {
    type: "Polygon";
    coordinates: number[][][];
  };
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const CARTODB_API_KEY = import.meta.env.VITE_CARTODB_API_KEY;
const TILE_URL = CARTODB_API_KEY
  ? `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=${CARTODB_API_KEY}`
  : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";

// Custom Leaflet DivIcon for Inaccessible Barrier Callout
const barrierIcon = L.divIcon({
  className: "custom-barrier-icon",
  html: '<div class="barrier-pin">🚫</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

const liftMaintenanceIcon = L.divIcon({
  className: "custom-lift-maint-icon",
  html: '<div class="barrier-pin warning">⚠️</div>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

// Station exit pin: exit code ("A", "2") with a lift badge — elevator, or struck-through when LTA reports an outage.
function exitIcon(exit: ExitCandidate) {
  const code = exit.exit_name.replace(/^exit\s+/i, "");
  const outage = exit.lift_status === "maintenance";
  const classes = ["exit-pin", exit.is_selected ? "selected" : "", outage ? "outage" : ""].join(" ");
  return L.divIcon({
    className: "exit-pin-icon",
    html: `<div class="${classes}"><span class="exit-pin-code">${code}</span><span class="exit-pin-lift${outage ? " down" : ""}" aria-hidden="true">🛗</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -16],
  });
}

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

function legStyle(mode: string, lineName?: string, accessibility?: string) {
  if (mode === "walk") {
    // Verified Step-Free / Ramp: Solid green line (#10b981)
    if (accessibility === "step_free" || accessibility === "ramp") {
      return { color: "#10b981", weight: 5, opacity: 0.95 };
    }
    // Stairs / Inaccessible Barriers: Dashed red line (#ef4444)
    if (accessibility === "stairs" || accessibility === "inaccessible" || accessibility === "lift_maintenance") {
      return { color: "#ef4444", weight: 5, dashArray: "4 6", opacity: 0.95 };
    }
    // Unknown walking leg
    return { color: "#687386", weight: 4, dashArray: "3 10", opacity: 0.85 };
  }
  if (mode === "bus") return { color: "#1b9b54", weight: 5 };
  const line = (lineName ?? "").toUpperCase();
  const mrtColors: Record<string, string> = {
    NS: "#d42d2d",
    EW: "#159947",
    NE: "#8c3fa8",
    CC: "#f09b27",
    DT: "#2469b1",
    TE: "#9a5a33",
    BP: "#76808e",
    CG: "#159947",
  };
  const prefix = Object.keys(mrtColors).find((code) => line.startsWith(code));
  return { color: prefix ? mrtColors[prefix] : "#2469b1", weight: 6 };
}

export default function App() {
  const [origin, setOrigin] = useState("Ang Mo Kio MRT Station");
  const [destination, setDestination] = useState("Singapore General Hospital");
  const [departureDate, setDepartureDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [departureTime, setDepartureTime] = useState(() => new Date().toTimeString().slice(0, 5));
  const [stepFree, setStepFree] = useState(true);
  const [showCovered, setShowCovered] = useState(true);
  const [showStationGround, setShowStationGround] = useState(true);
  const [showExits, setShowExits] = useState(true);
  const [simulateOutage, setSimulateOutage] = useState(false);
  const [simulatedStation, setSimulatedStation] = useState("NOVENA");
  const [dryRouteMode, setDryRouteMode] = useState(false);

  const [coveredLinkways, setCoveredLinkways] = useState<CoveredLinkwayFeature[]>([]);
  const [stationGroundPolygons, setStationGroundPolygons] = useState<StationGroundFeature[]>([]);
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [error, setError] = useState("");
  const originSuggestions = useLocationSuggestions(origin);
  const destinationSuggestions = useLocationSuggestions(destination);

  const routePoints: [number, number][] = route
    ? route.recommended_route.legs.flatMap((leg) => leg.geometry.map((point) => [point.lat, point.lon] as [number, number]))
    : [];
  const points: [number, number][] = routePoints.length > 1
    ? routePoints
    : route
    ? [[route.origin.lat, route.origin.lon], [route.destination.lat, route.destination.lon]]
    : [[1.3521, 103.8198]];

  // Compute sheltered linkways near active route
  const nearbyLinkwaysCount = route && routePoints.length > 0 ? coveredLinkways.filter((feat) => {
    const coords = feat.geometry.coordinates;
    const lats = routePoints.map((p) => p[0]);
    const lons = routePoints.map((p) => p[1]);
    const minLat = Math.min(...lats) - 0.006;
    const maxLat = Math.max(...lats) + 0.006;
    const minLon = Math.min(...lons) - 0.006;
    const maxLon = Math.max(...lons) + 0.006;
    if (feat.geometry.type === "LineString") {
      return (coords as number[][]).some(([lon, lat]) => lat >= minLat && lat <= maxLat && lon >= minLon && lon <= maxLon);
    } else if (feat.geometry.type === "MultiLineString") {
      return (coords as number[][][]).some((line) => line.some(([lon, lat]) => lat >= minLat && lat <= maxLat && lon >= minLon && lon <= maxLon));
    }
    return false;
  }).length : coveredLinkways.length;

  // Load CoveredLinkways
  useEffect(() => {
    if (!showCovered) {
      setCoveredLinkways([]);
      return;
    }
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/geo/covered-linkways?min_lat=1.15&max_lat=1.48&min_lon=103.60&max_lon=104.05`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: CoveredLinkwayFeature[]) => setCoveredLinkways(data))
      .catch((err) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) setCoveredLinkways([]);
      });
    return () => controller.abort();
  }, [showCovered]);

  // Load Station Ground Level Polygons (AmendmenttoMP2014RailStation)
  useEffect(() => {
    if (!showStationGround) {
      setStationGroundPolygons([]);
      return;
    }
    const controller = new AbortController();
    fetch(`${API_URL}/api/v1/geo/station-ground-levels?min_lat=1.15&max_lat=1.48&min_lon=103.60&max_lon=104.05`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((data: StationGroundFeature[]) => setStationGroundPolygons(data))
      .catch((err) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) setStationGroundPolygons([]);
      });
    return () => controller.abort();
  }, [showStationGround]);

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
        preferences: {
          stepFree,
          simulateLiftMaintenance: simulateOutage ? simulatedStation : null,
        },
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
        <header className="brand-header">
          <span className="persona-tag">Persona: Jane Koh (Motorized Wheelchair)</span>
          <h1>Smart Commuter</h1>
        </header>
        <form onSubmit={handleSubmit}>
          <input
            aria-label="Origin"
            placeholder="Origin"
            list="origin-suggestions"
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
            required
          />
          <datalist id="origin-suggestions">
            {originSuggestions.map((location) => <option key={location.address} value={location.address} />)}
          </datalist>

          <input
            aria-label="Destination"
            placeholder="Destination"
            list="destination-suggestions"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            required
          />
          <datalist id="destination-suggestions">
            {destinationSuggestions.map((location) => <option key={location.address} value={location.address} />)}
          </datalist>

          <div className="date-time">
            <input aria-label="Departure date" type="date" value={departureDate} onChange={(event) => setDepartureDate(event.target.value)} required />
            <input aria-label="Departure time" type="time" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} required />
          </div>

          <label className="preference-toggle">
            <input type="checkbox" checked={stepFree} onChange={(event) => setStepFree(event.target.checked)} aria-describedby="step-free-description" />
            <span>♿ Verified Step-Free Route</span>
          </label>
          <p className="preference-description" id="step-free-description">
            Avoid stairs, mandate lifts & ramps, confirm concourse level transitions.
          </p>

          <label className="preference-toggle">
            <input type="checkbox" checked={showCovered} onChange={(event) => setShowCovered(event.target.checked)} aria-describedby="sheltered-description" />
            <span>☂️ Sheltered Walkways (CoveredLinkWay)</span>
          </label>
          <p className="preference-description" id="sheltered-description">
            Highlight LTA weather-protected linkways for motorized wheelchairs.
          </p>

          <label className="preference-toggle dry-route-toggle">
            <input type="checkbox" checked={dryRouteMode} onChange={(event) => setDryRouteMode(event.target.checked)} aria-describedby="dry-route-description" />
            <span>🌧️ 100% Dry Route Mode</span>
          </label>
          <p className="preference-description" id="dry-route-description">
            When rain is forecasted, prefer continuous covered paths: concourse → underpass → covered linkway → canopy.
          </p>

          <div className="simulator-box">
            <label className="preference-toggle danger-toggle">
              <input type="checkbox" checked={simulateOutage} onChange={(e) => setSimulateOutage(e.target.checked)} />
              <span>⚠️ Disruption Simulator: Lift Outage</span>
            </label>
            {simulateOutage && (
              <div className="simulator-controls">
                <label>Simulate lift failure at station:</label>
                <select value={simulatedStation} onChange={(e) => setSimulatedStation(e.target.value)}>
                  <option value="NOVENA">Novena (Exit A Lift Down)</option>
                  <option value="BRADDELL">Braddell (Exit A Lift Down)</option>
                  <option value="ORCHARD">Orchard (Exit A Lift Down)</option>
                  <option value="OUTRAM PARK">Outram Park (Exit A Lift Down)</option>
                </select>
                <small>Demonstrates dynamic edge invalidation and rerouting around broken station lifts.</small>
              </div>
            )}
          </div>

          <button type="submit">Find Wheelchair Route</button>
        </form>

        {route && (
          <section className="route-details">
            <h2>{route.recommended_route.total_duration_min} min</h2>
            <p className="muted">{route.origin.label ?? "Origin"} to {route.destination.label ?? "Destination"}</p>

            {/* Sheltered Walkways Summary */}
            {showCovered && nearbyLinkwaysCount > 0 && (
              <div className="sheltered-summary">
                <strong>☂️ {nearbyLinkwaysCount} Sheltered Walkway segments along route</strong>
                <small>Continuous covered walkways protect motorized wheelchairs from tropical downpours.</small>
              </div>
            )}

            {/* Rain Forecast Banner */}
            {route.rain_forecast && (
              <div className={`rain-banner ${route.rain_forecast.rain_along_route ? "rain-warning" : "rain-clear"}`}>
                <div className="rain-banner-header">
                  {route.rain_forecast.rain_along_route ? (
                    <>
                      <span className="rain-icon">🌧️</span>
                      <strong>Rain Forecasted — 100% Dry Route Recommended</strong>
                    </>
                  ) : route.rain_forecast.currently_raining ? (
                    <>
                      <span className="rain-icon">🌦️</span>
                      <strong>Currently Raining — Use Sheltered Paths</strong>
                    </>
                  ) : (
                    <>
                      <span className="rain-icon">☀️</span>
                      <strong>No Rain Expected — Open-Air Route OK</strong>
                    </>
                  )}
                </div>
                <p className="rain-recommendation">{route.rain_forecast.recommendation}</p>
                {route.rain_forecast.rain_along_route && dryRouteMode && (
                  <div className="dry-badge-container">
                    <span className="badge-dry">✓ 100% DRY GUARANTEED</span>
                    <small>Using covered linkways, concourses, and underpasses only.</small>
                  </div>
                )}
              </div>
            )}

            {/* Station Exit Routing Info */}
            {route.recommended_route.exit_routing && (
              <>
                <p className={route.recommended_route.exit_routing.enabled ? "exit-note" : "exit-note unavailable"}>
                  {route.recommended_route.exit_routing.enabled ? (
                    <>
                      {route.recommended_route.exit_routing.explanation}
                      <br />
                      {route.recommended_route.exit_routing.destination && (
                        `Destination access: ${route.recommended_route.exit_routing.destination.station_name} — ${route.recommended_route.exit_routing.destination.exit_name}`
                      )}
                    </>
                  ) : route.recommended_route.exit_routing.fallback_reason === "no_mrt_segment" ? (
                    "Exit-level routing is unavailable because this journey has no MRT segment."
                  ) : (
                    "No verified MRT exit route was selected; the original station access route is retained."
                  )}
                </p>

                {route.recommended_route.exit_routing.destination && (
                  <details className="station-guide" open>
                    <summary>Inside {route.recommended_route.exit_routing.destination.station_name}: {route.recommended_route.exit_routing.destination.exit_name}</summary>
                    <p>After alighting at <strong>{route.recommended_route.exit_routing.destination.station_name}</strong>, follow station signs for <strong>{route.recommended_route.exit_routing.destination.exit_name}</strong>.</p>
                    {route.accessibility.step_free && (() => {
                      const selected = route.recommended_route.exit_routing?.candidate_exits?.find((exit) => exit.id === route.recommended_route.exit_routing?.destination?.exit_id);
                      return selected?.station_lift_alerts.length
                        ? <p className="highlight-text warning">⚠️ Other lift outages reported in this station: {selected.station_lift_alerts.join("; ")}. Allow extra time or ask station staff.</p>
                        : <p className="highlight-text">🛗 No lift outage reported by LTA for this exit. Use lifts and ramps; avoid escalators and stairs.</p>;
                    })()}
                  </details>
                )}
              </>
            )}

            {/* Accessibility & Decision Box */}
            {route.accessibility.step_free && (
              <div className={route.accessibility.accessible ? "accessibility ok" : "accessibility caution"}>
                <div className="accessibility-title">
                  <strong>{route.accessibility.accessible ? "✓ Verified Step-Free Route" : "⚠️ Accessibility Advisory"}</strong>
                  <span className="badge-pill">{route.accessibility.verification.toUpperCase()}</span>
                </div>
                <span>{route.decision.summary}</span>
                {route.decision.details.map((detail, idx) => (
                  <small key={idx} className="decision-detail-item">• {detail}</small>
                ))}
              </div>
            )}

            {/* Route Legs with Stairs/Ramp Badges */}
            <ol className="legs-list">
              {route.recommended_route.legs.map((leg, index) => {
                const isWalk = leg.mode === "walk";
                const isStepFree = leg.accessibility === "step_free" || leg.accessibility === "ramp";
                const isBarrier = leg.accessibility === "stairs" || leg.accessibility === "inaccessible" || leg.accessibility === "lift_maintenance";

                return (
                  <li key={index} className={isBarrier ? "leg-barrier" : isStepFree ? "leg-stepfree" : ""}>
                    <div className="leg-mode-col">
                      <strong>{leg.mode === "mrt" ? "MRT" : leg.mode}</strong>
                      {leg.line_name && <span className="line-badge">{leg.line_name}</span>}
                    </div>
                    <div className="leg-info-col">
                      <span>{leg.from} → {leg.to}</span>
                      {isWalk && (
                        <div className="leg-accessibility-tags">
                          {isStepFree && <span className="tag-stepfree">✓ Step-Free / Ramp</span>}
                          {leg.accessibility === "stairs" && <span className="tag-stairs">🚫 Stairs Barrier</span>}
                          {leg.accessibility === "lift_maintenance" && <span className="tag-barrier">⚠️ Severed: Lift Outage</span>}
                          {leg.accessibility === "unknown" && <span className="tag-unknown">? Unverified Walk</span>}
                        </div>
                      )}
                    </div>
                    <small className="leg-time">{leg.duration_min} min</small>
                  </li>
                );
              })}
            </ol>
          </section>
        )}

        {error && <p className="error" role="alert">{error}</p>}
      </section>

      <section className="map-shell" aria-label="Route map">
        {/* Floating Controls */}
        <div className="map-floating-panel">
          <label className="map-toggle-item">
            <input type="checkbox" checked={showCovered} onChange={(e) => setShowCovered(e.target.checked)} />
            <span>☂️ Sheltered Walkways</span>
            {showCovered && coveredLinkways.length > 0 && <span className="count-pill">{coveredLinkways.length.toLocaleString()}</span>}
          </label>
          <label className="map-toggle-item">
            <input type="checkbox" checked={showStationGround} onChange={(e) => setShowStationGround(e.target.checked)} />
            <span>🏛️ Station Footprints (GRND_LEVEL)</span>
            {showStationGround && stationGroundPolygons.length > 0 && (
              <span className="count-pill purple">{stationGroundPolygons.length}</span>
            )}
          </label>
          <label className="map-toggle-item">
            <input type="checkbox" checked={showExits} onChange={(e) => setShowExits(e.target.checked)} />
            <span>🚪 Station Exits</span>
            {showExits && (route?.recommended_route.exit_routing?.candidate_exits?.length ?? 0) > 0 && (
              <span className="count-pill">{route?.recommended_route.exit_routing?.candidate_exits?.length}</span>
            )}
          </label>
          {route?.rain_forecast?.rain_along_route && (
            <div className="map-dry-indicator">
              <span className="dry-indicator-dot"></span>
              <span>Rain Expected — Dry Mode {dryRouteMode ? "ON" : "OFF"}</span>
            </div>
          )}
        </div>

        {/* Enhanced Map Legend */}
        <div className="map-legend">
          <div className="legend-title">Map Layers & Accessibility</div>
          <div className="legend-item">
            <span className="legend-line stepfree-line"></span>
            <span>Verified Step-Free / Ramp (#10b981)</span>
          </div>
          <div className="legend-item">
            <span className="legend-line barrier-line"></span>
            <span>Stairs / Inaccessible Barrier (#ef4444)</span>
          </div>
          <div className="legend-item">
            <span className="legend-line sheltered-line"></span>
            <span>Covered Walkway (LTA)</span>
          </div>
          <div className="legend-item">
            <span className="legend-line walk-line"></span>
            <span>Standard Pedestrian Leg</span>
          </div>
          <div className="legend-item">
            <span className="legend-polygon underground-poly"></span>
            <span>Underground Station Footprint</span>
          </div>
          <div className="legend-item">
            <span className="legend-polygon elevated-poly"></span>
            <span>Elevated Station Footprint</span>
          </div>
          <div className="legend-item">
            <span className="legend-exit"><span className="exit-pin"><span className="exit-pin-code">A</span><span className="exit-pin-lift">🛗</span></span></span>
            <span>Station Exit — no lift outage reported</span>
          </div>
          <div className="legend-item">
            <span className="legend-exit"><span className="exit-pin outage"><span className="exit-pin-code">B</span><span className="exit-pin-lift down">🛗</span></span></span>
            <span>Station Exit — lift out of service</span>
          </div>
          <div className="legend-item">
            <span className="legend-exit"><span className="exit-pin selected"><span className="exit-pin-code">C</span><span className="exit-pin-lift">🛗</span></span></span>
            <span>Exit used by this route</span>
          </div>
        </div>

        <MapContainer center={points[0]} zoom={12} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>'
            url={TILE_URL}
            maxZoom={19}
          />

          {/* Station Ground Level Footprint Layer (AmendmenttoMP2014RailStation) */}
          {showStationGround && stationGroundPolygons.length > 0 && (
            <GeoJSON
              key={`station-ground-${stationGroundPolygons.length}`}
              data={{
                type: "FeatureCollection",
                features: stationGroundPolygons,
              } as any}
              style={(feature) => {
                const level = feature?.properties?.GRND_LEVEL;
                const isUnderground = level === "UNDERGROUND";
                return {
                  color: isUnderground ? "#7c3aed" : "#0284c7",
                  fillColor: isUnderground ? "#8b5cf6" : "#38bdf8",
                  fillOpacity: 0.22,
                  weight: 2.5,
                  dashArray: isUnderground ? "4 3" : undefined,
                };
              }}
              onEachFeature={(feature, layer) => {
                const name = feature.properties?.NAME ?? "Rail Station";
                const level = feature.properties?.GRND_LEVEL ?? "UNKNOWN";
                const stnType = feature.properties?.TYPE ?? "MRT";
                const isUnderground = level === "UNDERGROUND";

                layer.bindPopup(`
                  <div class="station-ground-popup">
                    <strong>🏛️ ${name} (${stnType})</strong>
                    <div class="ground-level-badge ${isUnderground ? "underground" : "aboveground"}">
                      ${level} CONCOURSE
                    </div>
                    <p class="concourse-desc">
                      ${
                        isUnderground
                          ? "Dual lift transfer required: Street ⬇️ Concourse ⬇️ Platform. Step-free route avoids all escalators and stairwells."
                          : "Elevated concourse: Street ⬆️ Platform via station elevator or ramp."
                      }
                    </p>
                  </div>
                `);
              }}
            />
          )}

          {/* Sheltered Walkways (CoveredLinkWay) */}
          {showCovered && coveredLinkways.length > 0 && (
            <GeoJSON
              key={`covered-linkways-${coveredLinkways.length}`}
              data={{
                type: "FeatureCollection",
                features: coveredLinkways,
              } as any}
              style={() => ({
                color: dryRouteMode && route?.rain_forecast?.rain_along_route ? "#059669" : "#0099ff",
                weight: dryRouteMode && route?.rain_forecast?.rain_along_route ? 5 : 3.5,
                dashArray: dryRouteMode && route?.rain_forecast?.rain_along_route ? undefined : "4 6",
                opacity: dryRouteMode && route?.rain_forecast?.rain_along_route ? 1.0 : 0.85,
              })}
              onEachFeature={(feature, layer) => {
                layer.bindPopup(`
                  <div class="linkway-popup">
                    <strong>${dryRouteMode && route?.rain_forecast?.rain_along_route ? "🌧️ 100% Dry Path" : "☂️ Sheltered Walkway"}</strong>
                    <p>LTA CoveredLinkWay Network (ID: ${feature.properties?.id ?? "N/A"})</p>
                    <span class="badge-sheltered">${dryRouteMode && route?.rain_forecast?.rain_along_route ? "Rain-Proof Continuous Coverage" : "Weather Protected (Rain & Sun)"}</span>
                  </div>
                `);
              }}
            />
          )}

          {/* Route Rendering */}
          {route && (
            <>
              <FitRoute points={points} />

              {/* Route Polyline Legs with Stairs/Ramps Differentiation */}
              {route.recommended_route.legs.map((leg, index) => {
                const geometry = leg.geometry.map((point) => [point.lat, point.lon] as [number, number]);
                if (geometry.length <= 1) return null;

                const isBarrier = leg.accessibility === "stairs" || leg.accessibility === "inaccessible" || leg.accessibility === "lift_maintenance";
                const midPoint = geometry[Math.floor(geometry.length / 2)];

                return (
                  <Fragment key={`leg-${index}`}>
                    <Polyline
                      positions={geometry}
                      pathOptions={legStyle(leg.mode, leg.line_name, leg.accessibility)}
                    >
                      <Popup>
                        <div className="leg-popup">
                          <strong>{leg.mode.toUpperCase()}: {leg.from} → {leg.to}</strong>
                          <p>Duration: {leg.duration_min} min</p>
                          <span className={`accessibility-pill ${leg.accessibility}`}>
                            {leg.accessibility === "step_free" || leg.accessibility === "ramp"
                              ? "✓ Verified Step-Free / Ramp"
                              : isBarrier
                              ? "🚫 Inaccessible Barrier / Stairs"
                              : "Standard Leg"}
                          </span>
                        </div>
                      </Popup>
                    </Polyline>

                    {/* Barrier Callout Marker if leg is inaccessible */}
                    {isBarrier && (
                      <Marker
                        position={midPoint}
                        icon={leg.accessibility === "lift_maintenance" ? liftMaintenanceIcon : barrierIcon}
                      >
                        <Popup>
                          <div className="barrier-popup">
                            <strong>🚫 Inaccessible Barrier Encountered</strong>
                            <p>
                              {leg.accessibility === "lift_maintenance"
                                ? "Station lift undergoing maintenance. Edge severed for wheelchair routing."
                                : "Staircase detected without ramp/lift access."}
                            </p>
                            <span className="badge-severed">Rerouted / Blocked</span>
                          </div>
                        </Popup>
                      </Marker>
                    )}
                  </Fragment>
                );
              })}

              {/* Candidate Station Exits with Lift Statuses */}
              {showExits && route.recommended_route.exit_routing?.candidate_exits?.map((exit) => {
                const isMaint = exit.lift_status === "maintenance";

                return (
                  <Marker
                    key={exit.id}
                    position={[exit.lat, exit.lon]}
                    icon={exitIcon(exit)}
                    zIndexOffset={exit.is_selected ? 1000 : isMaint ? 500 : 0}
                    title={`${exit.station_name} ${exit.exit_name}`}
                  >
                    <Popup>
                      <div className="exit-marker-popup">
                        <strong>{exit.station_name} — {exit.exit_name}</strong>
                        <div className={`lift-badge ${isMaint ? "down" : "active"}`}>
                          {isMaint ? <><s>🛗</s> Lift out of service{stepFree ? " — exit avoided" : ""}</> : "🛗 No lift outage reported"}
                        </div>
                        {exit.lift_alerts.map((alert) => <small key={alert} className="exit-alert">{alert}</small>)}
                        {exit.station_lift_alerts.length > 0 && (
                          <div className="station-lift-alerts">
                            <strong>⚠️ Other lift outages in this station</strong>
                            {exit.station_lift_alerts.map((alert) => <small key={alert}>{alert}</small>)}
                          </div>
                        )}
                        {exit.is_selected && <span className="selected-tag">★ Exit used by this route</span>}
                        <small className="exit-source">Lift status: LTA FacilitiesMaintenance</small>
                      </div>
                    </Popup>
                  </Marker>
                );
              })}

              {/* Origin Marker */}
              <CircleMarker
                center={[route.origin.lat, route.origin.lon]}
                radius={9}
                pathOptions={{ color: "#fff", fillColor: "#16803c", fillOpacity: 1, weight: 3 }}
              >
                <Popup>Origin: {route.origin.label}</Popup>
              </CircleMarker>

              {/* Destination Marker */}
              <CircleMarker
                center={[route.destination.lat, route.destination.lon]}
                radius={9}
                pathOptions={{ color: "#fff", fillColor: "#c43636", fillOpacity: 1, weight: 3 }}
              >
                <Popup>Destination: {route.destination.label}</Popup>
              </CircleMarker>
            </>
          )}
        </MapContainer>
      </section>
    </main>
  );
}
