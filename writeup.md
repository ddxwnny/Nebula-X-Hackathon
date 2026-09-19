# sMaRT Move

*Your journey, adapted to you.*

---

## Persona

We built sMaRT Move for **Jane Koh Swee Hoon**, 66, a retired administrative executive who uses a motorised wheelchair and lives independently in Ang Mo Kio. Jane values her autonomy and relies on MRT travel, but inaccessible routes can turn a small disruption into a journey-ending problem. Her core need is therefore not simply finding the fastest route, but knowing that she can complete the journey safely and independently.

---

## Architecture & Solution

sMaRT Move is an accessibility-first journey planning and disruption management layer built around three main components:

1. **Route Planning Engine:** Plans door-to-door, multi-modal journeys and prioritises step-free routes. It uses station-exit-level routing, lift/escalator outage information, live disruption alerts, and bridging bus/shuttle information to recalculate routes when conditions change.
2. **Geospatial Accessibility Layer:** Uses OpenStreetMap and provided geospatial data to distinguish accessible paths from stairs, represent station exits, and surface covered walkways. This allows the system to reason beyond station-to-station routing.
3. **Accessible Visualisation & Alerts:** Displays the original and alternative routes together, highlights affected segments, shows additional travel time, and provides plain-language explanations for route changes. The interface uses large text, large touch targets, high contrast, and non-colour-only status indicators.

The system also supports proactive alerts, such as notifying Jane before a planned lift outage affects her saved routine, and mid-journey rerouting when a disruption occurs ahead of her.

---

## Key Assumptions

Our prototype assumes that the required transport and geospatial data is available and sufficiently up to date, including:

* Train service disruption information
* Station facility and maintenance status
* Station exit locations
* OpenStreetMap pedestrian and accessibility data
* Bridging bus or shuttle information
* Crowd-level information where available

We also assume that accessibility information can be translated into route constraints, such as excluding a route that depends on an out-of-service lift. For the prototype, the default safety buffer is 30–45 minutes, based on the persona requirement specified in our product design, rather than a measured behavioural study.

---

## Limitations

sMaRT Move is a prototype, so its recommendations are only as reliable as the underlying data. Stale, incomplete, or incorrectly tagged accessibility data could result in an unsuitable route, particularly for street-level paths or station facilities.

The prototype also does not establish that every suggested route is physically accessible in real-world conditions. For example, temporary obstacles, unexpected crowding, or a lift becoming unavailable after the last data update may not be captured.

The staff-assistance feature is also specified as either a station-staff integration or a simulated endpoint for the demo, so we do not claim that the prototype can actually dispatch station staff.

Finally, we do not claim a measured accuracy improvement, time saving, or superiority over existing journey planners, because we have not conducted a controlled benchmark to establish these figures. The prototype's contribution is instead the integration of accessibility constraints, real-time disruptions, and proactive rerouting into a single journey experience.
