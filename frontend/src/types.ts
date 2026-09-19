export type RouteLeg = {
  mode: string;
  duration_min: number;
  distance_m?: number;
  from: string;
  to: string;
  geometry: Array<{ lat: number; lon: number }>;
  line_name?: string;
  line?: string;
};

export type RouteResponse = {
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

export type LocationSuggestion = {
  address: string;
  label?: string;
  lat?: number;
  lon?: number;
};

export type TrainDisruption = {
  line: string;
  direction?: string;
  stations: string[];
  free_public_bus?: string[];
  free_mrt_shuttle?: string[];
  mrt_shuttle_direction?: string;
};

export type TrainServiceStatus = {
  status: number;
  affected_segments: TrainDisruption[];
  messages: string[];
  data_status: string;
  timestamp?: string;
};

export type RerouteData = {
  status: string;
  previous_route: { remaining_duration_min: number };
  new_route: { remaining_duration_min: number; legs: RouteLeg[] };
  change: {
    additional_duration_min: number;
    reason: string | { type: string; message: string };
  };
};
