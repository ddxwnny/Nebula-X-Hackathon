import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type {
  LocationSuggestion,
  RouteLeg,
  RouteResponse,
  RerouteData,
  TrainServiceStatus,
} from "./types";
import {
  api,
  post,
  legColor,
  legLabel,
  lineInfo,
  minutes,
  clockTime,
  singaporeNow,
} from "./transit";
import {
  Announcement,
  Icon,
  InfoCard,
  Loading,
  SheetHandle,
} from "./components";

const EMPTY_LEGS: RouteLeg[] = [];
type Place = { text: string; coordinates?: { lat: number; lon: number } };
type Disruption = {
  line: string;
  affected_stations: string[];
  message?: string;
};
type JourneyStatus = {
  status: string;
  data_status: string;
  disruption?: Disruption;
};
function LocationField({
  label,
  place,
  onChange,
}: {
  label: string;
  place: Place;
  onChange: (place: Place) => void;
}) {
  const [suggestions, setSuggestions] = useState<LocationSuggestion[]>([]);
  const [state, setState] = useState("");
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    setSuggestions([]);
    setState("");
    if (place.text.trim().length < 2 || place.coordinates) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setState("loading");
      try {
        const result = await api<LocationSuggestion[]>(
          `/locations/search?query=${encodeURIComponent(place.text)}`,
          { signal: controller.signal },
        );
        setSuggestions(result);
        setState(
          result.length
            ? ""
            : "No suggestions. Try a station, street, or postal code.",
        );
      } catch {
        if (!controller.signal.aborted)
          setState(
            "Suggestions unavailable. You can still enter a full address.",
          );
      }
    }, 300);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [place.text, place.coordinates]);
  return (
    <div
      className="location-field"
      onFocus={() => setFocused(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false);
      }}
    >
      <label htmlFor={label}>{label}</label>
      <div className="input-with-icon">
        <Icon name={label === "From" ? "location" : "pin"} />
        <input
          id={label}
          autoComplete="off"
          placeholder={
            label === "From"
              ? "Where are you starting?"
              : "Where would you like to go?"
          }
          value={place.text}
          onChange={(e) => onChange({ text: e.target.value })}
          required
          aria-describedby={`${label}-status`}
          onKeyDown={(e) => {
            if (e.key === "Escape") setFocused(false);
          }}
        />
      </div>
      {focused && (
        <div className="suggestions">
          <span id={`${label}-status`} className="field-status">
            {state === "loading" ? <Loading>Finding places…</Loading> : state}
          </span>
          {suggestions.slice(0, 5).map((item, i) => (
            <button
              key={`${item.address}-${i}`}
              type="button"
              onClick={() => {
                onChange({
                  text: item.address,
                  coordinates:
                    item.lat != null && item.lon != null
                      ? { lat: item.lat, lon: item.lon }
                      : undefined,
                });
                setFocused(false);
              }}
            >
              <Icon name="pin" size={16} />
              {item.address}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
function MapViewport({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1)
      map.fitBounds(points, { padding: [30, 30], maxZoom: 16 });
  }, [map, points]);
  useEffect(() => {
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => map.invalidateSize({ pan: false }));
    });
    observer.observe(map.getContainer());
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [map]);
  return null;
}
function RouteBadge({ leg }: { leg: RouteLeg }) {
  const mode = leg.mode.toLowerCase();
  return (
    <span
      className={`route-badge ${mode === "walk" ? "walking" : ""}`}
      style={
        {
          "--line": legColor(leg),
          color:
            lineInfo(leg.line_name ?? leg.line)?.code === "CC" &&
            mode !== "walk"
              ? "#302600"
              : undefined,
        } as CSSProperties
      }
    >
      <Icon
        name={mode === "walk" ? "walk" : mode === "bus" ? "bus" : "train"}
        size={14}
      />
      {mode === "walk"
        ? minutes(leg.duration_min)
        : mode === "bus"
          ? legLabel(leg)
          : (lineInfo(leg.line_name ?? leg.line)?.code ?? legLabel(leg))}
    </span>
  );
}
export default function App() {
  const [tab, setTab] = useState<"plan" | "alerts">("plan");
  const [origin, setOrigin] = useState<Place>({ text: "" });
  const [destination, setDestination] = useState<Place>({ text: "" });
  const [scheduled, setScheduled] = useState(false);
  const [date, setDate] = useState(singaporeNow().date);
  const [time, setTime] = useState(singaporeNow().time);
  const [stepFree, setStepFree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");
  const [showResults, setShowResults] = useState(false);
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [plannedAt, setPlannedAt] = useState(new Date());
  const [alternativeAt, setAlternativeAt] = useState(new Date());
  const [alternativeOrigin, setAlternativeOrigin] = useState<{
    lat: number;
    lon: number;
    label?: string;
  } | null>(null);
  const [network, setNetwork] = useState<TrainServiceStatus | null>(null);
  const [networkError, setNetworkError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [statusBusy, setStatusBusy] = useState(true);
  const [online, setOnline] = useState(navigator.onLine);
  const [details, setDetails] = useState(true);
  const [sheetHeight, setSheetHeight] = useState(60);
  const workspaceRef = useRef<HTMLElement>(null);
  const [journey, setJourney] = useState<JourneyStatus | null>(null);
  const [monitorError, setMonitorError] = useState("");
  const [preview, setPreview] = useState<RerouteData | null>(null);
  const [accepted, setAccepted] = useState<RerouteData | null>(null);
  const [rerouting, setRerouting] = useState(false);
  const [rerouteError, setRerouteError] = useState("");
  const [scope, setScope] = useState("journey");
  const [categories, setCategories] = useState([
    "Train",
    "Bus",
    "Weather",
    "Accessibility",
  ]);
  const [mapError, setMapError] = useState(false);
  const resultsRef = useRef<HTMLElement>(null);
  const detailsButtonRef = useRef<HTMLButtonElement>(null);
  const previewVersion = useRef(0);
  const legs =
    accepted?.new_route.legs ?? route?.recommended_route.legs ?? EMPTY_LEGS;
  const duration =
    accepted?.new_route.remaining_duration_min ??
    route?.recommended_route.total_duration_min ??
    0;
  const remaining = legs;
  const currentPosition = accepted ? alternativeOrigin : route?.origin;
  const disruption = journey?.disruption;
  const disruptionKey = JSON.stringify(disruption ?? null);
  useEffect(() => {
    setPreview(null);
    previewVersion.current++;
  }, [disruptionKey]);
  const serviceUnavailable =
    networkError || !network || network.data_status !== "ok";
  const serviceText = serviceUnavailable
    ? network?.data_status === "stale" || (networkError && network)
      ? "Service information may be out of date"
      : "Service status unavailable"
    : network.status === 2
      ? "Train service disruption reported"
      : network.status === 1
        ? "No train disruptions reported"
        : "Service status unavailable";
  const points = useMemo<[number, number][]>(() => {
    const geometry = legs.flatMap((leg) =>
      (leg.geometry ?? []).map((p) => [p.lat, p.lon] as [number, number]),
    );
    return geometry.length > 1
      ? geometry
      : route
        ? [
            [route.origin.lat, route.origin.lon],
            [route.destination.lat, route.destination.lon],
          ]
        : [[1.3521, 103.8198]];
  }, [legs, route]);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    async function update() {
      setStatusBusy(true);
      try {
        const data = await api<TrainServiceStatus>("/disruptions/status");
        if (!cancelled) {
          setNetwork(data);
          setNetworkError(false);
        }
      } catch {
        if (!cancelled) setNetworkError(true);
      } finally {
        if (!cancelled) {
          setStatusBusy(false);
          timer = window.setTimeout(update, 30000);
        }
      }
    }
    void update();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [refresh, online]);
  function journeyPayload() {
    return {
      route_id: route?.request_id ?? "route",
      origin: currentPosition ?? route?.origin,
      destination: route?.destination,
      current_position: currentPosition ?? route?.origin,
      legs: remaining.map((leg) => ({
        ...leg,
        line: leg.line_name ?? leg.line,
      })),
    };
  }
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    setJourney(null);
    setMonitorError("");
    setPreview(null);
    setRerouteError("");
    previewVersion.current++;
    if (!route) return;
    async function monitor() {
      try {
        const registered = await api<{ journey_id: string }>(
          "/journeys",
          post(journeyPayload()),
        );
        async function poll() {
          if (cancelled) return;
          try {
            const status = await api<JourneyStatus>(
              `/journeys/${registered.journey_id}/status`,
            );
            if (!cancelled) {
              setJourney(status);
              setMonitorError(
                status.data_status === "ok"
                  ? ""
                  : "Journey alerts may be out of date. Check service announcements.",
              );
            }
          } catch {
            if (!cancelled)
              setMonitorError(
                "Journey updates unavailable. Your route is still here.",
              );
          }
          if (!cancelled) timer = window.setTimeout(poll, 30000);
        }
        await poll();
      } catch {
        if (!cancelled)
          setMonitorError(
            "Journey updates unavailable. Your route is still here.",
          );
      }
    }
    void monitor();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [route, accepted, refresh, online]);
  async function plan(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    const now = singaporeNow();
    const departure = scheduled
      ? new Date(`${date}T${time}:00+08:00`)
      : new Date();
    if (scheduled && departure.getTime() < Date.now() - 60000) {
      setError("Choose a departure time in the future (Singapore time).");
      setBusy(false);
      return;
    }
    try {
      const result = await api<RouteResponse>(
        "/routes/plan",
        post({
          origin: origin.coordinates
            ? { ...origin.coordinates, address: origin.text }
            : { address: origin.text.trim() },
          destination: destination.coordinates
            ? { ...destination.coordinates, address: destination.text }
            : { address: destination.text.trim() },
          departure_date: scheduled ? date : now.date,
          departure_time: scheduled ? time : now.time,
          preferences: { stepFree },
        }),
      );
      if (!result.recommended_route.legs.length)
        throw new Error(
          "No route found. Try another departure time or nearby location.",
        );
      setRoute(result);
      setShowResults(true);
      setPlannedAt(departure);
      setAccepted(null);
      setPreview(null);

      setDetails(true);
      setSheetHeight(60);
      window.setTimeout(() => resultsRef.current?.focus(), 100);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to plan this journey. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  function locate() {
    if (!navigator.geolocation) {
      setError(
        "Location is unavailable in this browser. Enter your starting point instead.",
      );
      return;
    }
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setOrigin({
          text: "Your location",
          coordinates: {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
          },
        });
        setLocating(false);
      },
      () => {
        setError(
          "We couldn’t access your location. Enter your starting point instead.",
        );
        setLocating(false);
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  }
  async function findAlternative() {
    if (rerouting || !route) return;
    if (!currentPosition) {
      setRerouteError(
        "Your current stop has no mapped position. Plan a new route from your current location.",
      );
      return;
    }
    const version = ++previewVersion.current;
    setRerouting(true);
    setRerouteError("");
    try {
      // Preview on a separate journey: the existing reroute endpoint mutates server state.
      const candidate = await api<{ journey_id: string }>(
        "/journeys",
        post(journeyPayload()),
      );
      await api(`/journeys/${candidate.journey_id}/status`);
      const result = await api<RerouteData>(
        `/journeys/${candidate.journey_id}/reroute`,
        { method: "POST" },
      );
      if (!result.new_route.legs.length)
        throw new Error(
          "No alternative found. Your current route has been kept.",
        );
      if (version === previewVersion.current) setPreview(result);
    } catch (err) {
      if (version === previewVersion.current)
        setRerouteError(
          err instanceof Error ? err.message : "Unable to find an alternative.",
        );
    } finally {
      setRerouting(false);
    }
  }
  const walkTime = legs
    .filter((leg) => leg.mode.toLowerCase() === "walk")
    .reduce((sum, leg) => sum + leg.duration_min, 0);
  const transfers = Math.max(
    0,
    legs.filter((leg) => leg.mode.toLowerCase() !== "walk").length - 1,
  );
  const arrival = clockTime(
    new Date(
      (accepted ? alternativeAt : plannedAt).getTime() + duration * 60000,
    ),
  );
  const exit = !accepted ? route?.recommended_route.exit_routing : undefined;
  const visibleSegments = (network?.affected_segments ?? []).filter(
    (segment) =>
      scope === "all" ||
      remaining.some((leg) => {
        const known = lineInfo(leg.line_name ?? leg.line);
        const affected = lineInfo(segment.line);
        return known && affected
          ? known.code === affected.code
          : (leg.line_name ?? leg.line)?.toUpperCase() ===
              segment.line.toUpperCase();
      }),
  );
  return (
    <div className="app">
      <header className="app-header">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("plan");
          }}
        >
          <span className="brand-mark">
            <Icon name="train" size={24} />
          </span>
          <span>
            sMaRT <span className="brand-light">Move</span>
            <small>A little clarity. Every journey.</small>
          </span>
        </a>
        <span className="header-meta">
          <span className="status-dot" />
          SINGAPORE <span className="header-divider">/</span> PUBLIC TRANSPORT
        </span>
        <button
          className="icon-button header-alert"
          aria-label="Open alerts"
          onClick={() => setTab("alerts")}
        >
          <Icon name="bell" />
          {network?.status === 2 && <span className="notification-dot" />}
        </button>
      </header>
      <Announcement messages={network?.messages ?? []} />
      {!online && (
        <div className="offline" role="status">
          You’re offline. Your current itinerary remains available; live updates
          need a connection.
        </div>
      )}
      <main
        ref={workspaceRef}
        style={{ "--sheet-height": `${sheetHeight}%` } as CSSProperties}
        className={`workspace ${tab === "alerts" ? "show-alerts" : ""} ${route && showResults ? "has-route" : ""} `}
      >
        <section
          className="planner-panel"
          hidden={tab !== "plan" || showResults}
          aria-label="Plan your journey"
        >
          <div className="eyebrow">EVERYDAY PLACES. BETTER JOURNEYS.</div>
          <h1>
            Where to today<span>?</span>
          </h1>
          <p className="intro">
            Find your way by train, bus, and a little walking.
          </p>
          <form onSubmit={plan} aria-busy={busy}>
            <div className="locations">
              <LocationField label="From" place={origin} onChange={setOrigin} />
              <button
                className="swap icon-button"
                type="button"
                aria-label="Swap origin and destination"
                onClick={() => {
                  setOrigin(destination);
                  setDestination(origin);
                }}
              >
                <Icon name="swap" size={18} />
              </button>
              <LocationField
                label="To"
                place={destination}
                onChange={setDestination}
              />
            </div>
            <button
              className="text-button locate"
              type="button"
              disabled={locating}
              onClick={locate}
            >
              {locating ? (
                <Loading>Finding your location…</Loading>
              ) : (
                <>
                  <Icon name="location" size={16} />
                  Use my location
                </>
              )}
            </button>
            <div className="departure-row">
              <Icon name="clock" size={19} />
              <label htmlFor="departure">Departure</label>
              <select
                id="departure"
                value={scheduled ? "later" : "now"}
                onChange={(e) => setScheduled(e.target.value === "later")}
              >
                <option value="now">Leave now</option>
                <option value="later">Schedule a trip</option>
              </select>
            </div>
            {scheduled && (
              <div className="date-time">
                <label>
                  Date
                  <input
                    type="date"
                    value={date}
                    min={singaporeNow().date}
                    required
                    onChange={(e) => setDate(e.target.value)}
                  />
                </label>
                <label>
                  Time (SGT)
                  <input
                    type="time"
                    value={time}
                    required
                    onChange={(e) => setTime(e.target.value)}
                  />
                </label>
              </div>
            )}
            <label className="checkbox preference">
              <input
                type="checkbox"
                checked={stepFree}
                onChange={(e) => setStepFree(e.target.checked)}
              />
              <span>
                <strong>Step-free route</strong>
                <small>Avoid stairs. Prefer lifts and ramps.</small>
              </span>
              <Icon name="access" />
            </label>
            <div className="conditions">
              <span>
                <Icon name="train" size={16} />
                {statusBusy && !network
                  ? "Checking train services…"
                  : serviceText}
              </span>
              <span>
                <Icon name="cloud" size={16} />
                Weather updates unavailable
              </span>
            </div>
            <button
              className="primary find-route"
              disabled={busy || rerouting || !online}
              type="submit"
            >
              {busy ? (
                <Loading>Finding your route…</Loading>
              ) : (
                <>
                  Find route
                  <Icon name="arrow" />
                </>
              )}
            </button>
            {error && (
              <div className="error-message" role="alert">
                {error}
              </div>
            )}
          </form>
          {route && (
            <button
              className="text-button"
              onClick={() => setShowResults(true)}
            >
              Return to current route
            </button>
          )}
          <div className="planner-footer">
            <Icon name="info" size={16} />
            <p>
              One journey, all the details.
              <br />
              Check your route for transfers and station exits.
            </p>
          </div>
        </section>
        {route && showResults && tab === "plan" && (
          <section
            className="map-shell"
            hidden={tab !== "plan"}
            aria-label="Journey map"
          >
            <MapContainer
              center={[1.3521, 103.8198]}
              zoom={12}
              scrollWheelZoom
              className="journey-map"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                eventHandlers={{ tileerror: () => setMapError(true) }}
              />
              <MapViewport points={points} />
              {legs.map(
                (leg, i) =>
                  leg.geometry?.length > 1 && (
                    <Polyline
                      key={`${accepted ? "new" : "old"}-${i}`}
                      positions={leg.geometry.map(
                        (p) => [p.lat, p.lon] as [number, number],
                      )}
                      pathOptions={{
                        color: legColor(leg),
                        weight: leg.mode.toLowerCase() === "walk" ? 4 : 6,
                        dashArray:
                          leg.mode.toLowerCase() === "walk" ? "3 9" : undefined,
                      }}
                    />
                  ),
              )}
              {route && (
                <>
                  <CircleMarker
                    center={[
                      accepted && alternativeOrigin
                        ? alternativeOrigin.lat
                        : route.origin.lat,
                      accepted && alternativeOrigin
                        ? alternativeOrigin.lon
                        : route.origin.lon,
                    ]}
                    radius={7}
                    pathOptions={{
                      color: "#fff",
                      fillColor: "#6550d7",
                      fillOpacity: 1,
                      weight: 3,
                    }}
                  >
                    <Popup>
                      {accepted
                        ? (alternativeOrigin?.label ?? "Current position")
                        : (route.origin.label ?? "Origin")}
                    </Popup>
                  </CircleMarker>
                  <CircleMarker
                    center={[route.destination.lat, route.destination.lon]}
                    radius={9}
                    pathOptions={{
                      color: "#fff",
                      fillColor: "#d64758",
                      fillOpacity: 1,
                      weight: 3,
                    }}
                  >
                    <Popup>{route.destination.label ?? "Destination"}</Popup>
                  </CircleMarker>
                </>
              )}
            </MapContainer>
            {mapError && (
              <div className="map-notice" role="status">
                Map tiles unavailable. You can still use the written journey
                directions.
              </div>
            )}
          </section>
        )}
        {route && showResults && tab === "plan" && (
          <section
            className="results-panel"
            ref={resultsRef}
            tabIndex={-1}
            aria-label="Journey results"
          >
            <SheetHandle
              value={sheetHeight}
              onChange={setSheetHeight}
              containerRef={workspaceRef}
            />
            <div className="sheet-content">
              <button
                className="text-button"
                onClick={() => setShowResults(false)}
              >
                ‹ Edit trip
              </button>
              <div className="result-heading">
                <span className="eyebrow">
                  {accepted
                    ? "ALTERNATIVE JOURNEY"
                    : "YOUR PUBLIC TRANSPORT ROUTE"}
                </span>
                <button
                  className="icon-button"
                  aria-label={
                    details ? "Hide journey details" : "Show journey details"
                  }
                  ref={detailsButtonRef}
                  onClick={() => setDetails(!details)}
                >
                  <Icon name={details ? "close" : "chevron"} size={18} />
                </button>
              </div>
              <div className="duration">
                <h2>
                  {Math.ceil(duration)}
                  <span> min</span>
                </h2>
                <span className="arrival">
                  Arrive ~{arrival}
                  <small>Estimated · Singapore time</small>
                </span>
              </div>
              <p className="route-endpoints">
                {accepted
                  ? (alternativeOrigin?.label ?? "Current position")
                  : (route.origin.label ?? "Origin")}
                <Icon name="arrow" size={15} />
                {route.destination.label ?? "Destination"}
              </p>
              <div className="route-chain">
                {legs.map((leg, i) => (
                  <RouteBadge key={i} leg={leg} />
                ))}
              </div>
              <div className="route-stats">
                <span>
                  <Icon name="walk" size={15} />
                  {minutes(walkTime)} walking
                </span>
                <span>
                  {transfers} transfer{transfers === 1 ? "" : "s"}
                </span>
              </div>
              {monitorError && (
                <div className="inline-notice">
                  {monitorError}
                  <button
                    className="text-button"
                    onClick={() => setRefresh((i) => i + 1)}
                  >
                    Retry updates
                  </button>
                </div>
              )}
              {disruption && (
                <div className="journey-warning" role="alert">
                  <strong>
                    <Icon name="bell" size={18} />
                    Your route is affected
                  </strong>
                  <p>
                    {disruption.line} ·{" "}
                    {disruption.affected_stations.join(" → ")}
                  </p>
                  {disruption.message && <p>{disruption.message}</p>}
                  <button
                    className="secondary"
                    disabled={rerouting || busy}
                    onClick={findAlternative}
                  >
                    {rerouting ? (
                      <Loading>Finding an alternative…</Loading>
                    ) : (
                      "View alternative"
                    )}
                  </button>
                </div>
              )}
              {rerouteError && (
                <p className="error-message" role="alert">
                  {rerouteError}
                </p>
              )}
              {preview && (
                <div className="alternative">
                  <span className="eyebrow">ALTERNATIVE AVAILABLE</span>
                  <h3>
                    {minutes(preview.new_route.remaining_duration_min)}
                    <small>
                      {" "}
                      ·{" "}
                      {(() => {
                        const diff = Math.round(
                          preview.new_route.remaining_duration_min -
                            preview.previous_route.remaining_duration_min,
                        );
                        return diff === 0
                          ? "same duration"
                          : `${Math.abs(diff)} min ${diff > 0 ? "longer" : "quicker"}`;
                      })()}
                    </small>
                  </h3>
                  <div className="route-chain">
                    {preview.new_route.legs.map((leg, i) => (
                      <RouteBadge key={i} leg={leg} />
                    ))}
                  </div>
                  <p>
                    {typeof preview.change.reason === "string"
                      ? preview.change.reason
                      : preview.change.reason.message}
                  </p>
                  <small>
                    Step-free access and station exits have not been verified
                    for this alternative.
                  </small>
                  <div className="button-row">
                    <button
                      className="primary"
                      onClick={() => {
                        setAlternativeOrigin(
                          currentPosition
                            ? { ...currentPosition, label: remaining[0]?.from }
                            : null,
                        );
                        setAccepted(preview);
                        setPreview(null);

                        setAlternativeAt(new Date());
                        setDetails(true);
                      }}
                    >
                      Use alternative
                    </button>
                    <button
                      className="secondary"
                      onClick={() => setPreview(null)}
                    >
                      Keep current
                    </button>
                  </div>
                </div>
              )}
              {accepted && (
                <button
                  className="text-button"
                  onClick={() => {
                    setAccepted(null);
                  }}
                >
                  Compare original route (
                  {minutes(route.recommended_route.total_duration_min)})
                </button>
              )}
              {details && (
                <div className="journey-details">
                  <div className="section-heading">
                    <h3>Route details</h3>
                    <span>{legs.length} sections</span>
                  </div>
                  {accepted ? (
                    <div className="inline-notice">
                      Accessibility and exit details are unverified for this
                      alternative.
                    </div>
                  ) : (
                    route.accessibility.step_free && (
                      <div
                        className={`access-note ${route.accessibility.accessible ? "verified" : ""}`}
                      >
                        <Icon name="access" />
                        <div>
                          <strong>
                            {route.accessibility.accessible
                              ? "Verified step-free route"
                              : "Step-free access not fully verified"}
                          </strong>
                          <p>{route.decision.summary}</p>
                          {route.decision.details.map((detail, i) => (
                            <small key={i}>{detail}</small>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                  {exit && (
                    <details className="exit-guide">
                      <summary>Station entrances & exits</summary>
                      {exit.origin && (
                        <p>
                          <strong>Enter {exit.origin.station_name}</strong>
                          <br />
                          {exit.origin.exit_name}
                        </p>
                      )}
                      {exit.destination && (
                        <p>
                          <strong>Leave {exit.destination.station_name}</strong>
                          <br />
                          {exit.destination.exit_name}
                        </p>
                      )}
                      {(!exit.enabled || exit.fallback_to_station_centroid) && (
                        <p>
                          Some station exits could not be verified. Follow
                          station signs for those connections.
                        </p>
                      )}
                    </details>
                  )}
                  <ol className="timeline">
                    {legs.map((leg, i) => (
                      <li
                        key={i}

                        style={{ "--line": legColor(leg) } as CSSProperties}
                      >
                        <span className="step-marker">{i + 1}</span>
                        <div className="leg-content">
                          <div className="leg-title">
                            <strong>{legLabel(leg)}</strong>
                            <span>{minutes(leg.duration_min)}</span>
                          </div>
                          <p>
                            {leg.mode.toLowerCase() === "walk"
                              ? "Walk from"
                              : "Board at"}{" "}
                            <strong>{leg.from}</strong>
                          </p>
                          <p>
                            {leg.mode.toLowerCase() === "walk"
                              ? "Continue to"
                              : "Alight at"}{" "}
                            <strong>{leg.to}</strong>
                          </p>
                          {!!leg.distance_m && (
                            <small>
                              {leg.distance_m < 1000
                                ? `${Math.round(leg.distance_m)} m`
                                : `${(leg.distance_m / 1000).toFixed(1)} km`}
                            </small>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                  <div className="destination-marker">
                    <Icon name="pin" />
                    <div>
                      <strong>Your destination</strong>
                      <p>{route.destination.label}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}
        {tab === "alerts" && (
          <section className="alerts-page">
            <div className="eyebrow">A LITTLE HEADS-UP GOES A LONG WAY</div>
            <h1>
              Travel updates<span>.</span>
            </h1>
            <p className="intro">
              Know what’s happening before your next connection.
            </p>
            <div className="alert-toolbar">
              <div className="segmented" aria-label="Alert scope">
                <button
                  aria-pressed={scope === "journey"}
                  onClick={() => setScope("journey")}
                >
                  My journey
                </button>
                <button
                  aria-pressed={scope === "all"}
                  onClick={() => setScope("all")}
                >
                  All services
                </button>
              </div>
              <button
                className="secondary"
                disabled={statusBusy}
                onClick={() => setRefresh((i) => i + 1)}
              >
                {statusBusy ? <Loading>Updating…</Loading> : "Refresh updates"}
              </button>
            </div>
            <fieldset className="alert-filters">
              <legend>Show updates for</legend>
              {["Train", "Bus", "Weather", "Accessibility"].map((category) => (
                <label className="checkbox" key={category}>
                  <input
                    type="checkbox"
                    checked={categories.includes(category)}
                    onChange={() =>
                      setCategories((current) =>
                        current.includes(category)
                          ? current.filter((c) => c !== category)
                          : [...current, category],
                      )
                    }
                  />
                  {category}
                </label>
              ))}
            </fieldset>
            {scope === "journey" && !route && (
              <InfoCard
                icon="map"
                title="Plan a journey to see relevant alerts"
              >
                <p>
                  Choose your destination first, or select All services to check
                  the network.
                </p>
                <button className="text-button" onClick={() => setTab("plan")}>
                  Plan a journey
                  <Icon name="arrow" size={16} />
                </button>
              </InfoCard>
            )}
            {categories.length === 0 && (
              <p>Select a category to see updates.</p>
            )}
            <div className="alert-grid">
              {categories.includes("Train") && (
                <>
                  <InfoCard
                    icon="train"
                    title={serviceText}
                    tone={
                      serviceUnavailable
                        ? ""
                        : network?.status === 2
                          ? "warning"
                          : "success"
                    }
                  >
                    <p>
                      {serviceUnavailable
                        ? "We can’t confirm current train conditions. Check station announcements and refresh before travelling."
                        : "Source: LTA train service alerts."}
                    </p>
                    {network?.timestamp && (
                      <small>
                        Source updated{" "}
                        {new Date(network.timestamp).toLocaleDateString(
                          "en-SG",
                          { timeZone: "Asia/Singapore" },
                        )}
                        , {clockTime(network.timestamp)}
                      </small>
                    )}
                  </InfoCard>
                  {(scope === "all" || route) &&
                    visibleSegments.map((segment, i) => (
                      <InfoCard
                        key={i}
                        icon="bell"
                        title={`${segment.line} · Service disruption`}
                        tone="warning"
                      >
                        <p>{segment.stations.join(" → ")}</p>
                        {segment.direction && (
                          <p>Towards {segment.direction}</p>
                        )}
                        {!!segment.free_public_bus?.length && (
                          <p>
                            Free public buses:{" "}
                            {segment.free_public_bus.join(", ")}
                          </p>
                        )}
                        {!!segment.free_mrt_shuttle?.length && (
                          <p>
                            Shuttle services:{" "}
                            {segment.free_mrt_shuttle.join(", ")}
                          </p>
                        )}
                        <small>
                          {scope === "journey"
                            ? "This line is on your route. Journey monitoring checks affected sections."
                            : "Check the affected stations before travelling."}
                        </small>
                      </InfoCard>
                    ))}
                </>
              )}
              {categories.includes("Weather") && (
                <InfoCard icon="cloud" title="Weather updates unavailable">
                  <p>
                    Rain forecasts and sheltered-route comparisons are not
                    available yet.
                  </p>
                  <span className="neutral-pill">
                    No live weather information
                  </span>
                </InfoCard>
              )}
              {categories.includes("Bus") && (
                <InfoCard icon="bus" title="Bus service updates unavailable">
                  <p>
                    Bus journey directions are available when returned by the
                    planner. Live bus delays are not currently available.
                  </p>
                </InfoCard>
              )}
              {categories.includes("Accessibility") && (
                <InfoCard
                  icon="access"
                  title={
                    route && !accepted && route.accessibility.step_free
                      ? route.accessibility.accessible
                        ? "Your route is verified step-free"
                        : "Your route has unverified access"
                      : "Plan with step-free access"
                  }
                >
                  <p>
                    {route && !accepted && route.accessibility.step_free
                      ? route.decision.summary
                      : "Select Step-free route when planning to check available lift and ramp information."}
                  </p>
                  {route &&
                    !accepted &&
                    route.accessibility.lifts_used.map((lift) => (
                      <p key={lift.id}>
                        {lift.station_exit ?? lift.id} · {lift.status}
                      </p>
                    ))}
                </InfoCard>
              )}
            </div>
            {!!network?.messages.length && (
              <section className="all-announcements">
                <h2>Service announcements</h2>
                {network.messages.map((message, i) => (
                  <p key={i}>{message}</p>
                ))}
              </section>
            )}
          </section>
        )}
      </main>
      <nav className="bottom-nav" aria-label="Main navigation">
        <button
          aria-current={tab === "plan" ? "page" : undefined}
          onClick={() => setTab("plan")}
        >
          <Icon name="map" />
          <span>Plan</span>
        </button>
        <button
          aria-current={tab === "alerts" ? "page" : undefined}
          onClick={() => setTab("alerts")}
        >
          <Icon name="bell" />
          <span>Alerts</span>
          {network?.status === 2 && <span className="nav-badge">!</span>}
        </button>
        <span className="nav-caption">Made for the everyday journey.</span>
      </nav>
    </div>
  );
}
