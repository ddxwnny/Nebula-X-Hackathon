# Public transport frontend — proposal for approval

Status: approved by the user; available frontend flows implemented on `frontend`.
Branch: `frontend`. No changes to `main`.

## Direction

Build a phone-layout public journey planner from the supplied wireframes. Following the user’s latest direction, keep a single-column mobile interface at every browser width: full-width on small phones and centred at a maximum width of 430px on larger screens. Keep the light background, purple primary action, map-led route results, and detailed transit itinerary. Use MRT line colours from the supplied reference consistently across badges, map segments, and itinerary rails; pair every colour with a line code/name. Exact colour values should be verified against an authoritative reference during implementation.

## Proposed screens and changes

1. **Plan:** visible Origin and Destination labels, address suggestions, a swap button, and an optional Use my location action with a manual-entry fallback. Default to Leave now; reveal date/time controls when scheduling. Keep the step-free preference with plain-language guidance. Place a compact journey conditions summary above Find route. Use the supplied announcement-banner pattern at the top for general notices; the proposed handling of urgent journey alerts is described below.
2. **Route results:** map above a resizable bottom panel on mobile; side-by-side layout on desktop. Each route card shows estimated duration, arrival time, walking time, transfers, and a compact walk → MRT → bus sequence. Explain the recommendation with supported facts. Show alternatives only when returned by the service. Omit driving, tolls, cycling, and flight controls from the public-transport reference image.
3. **Journey details:** replace the dense table with a vertical, numbered timeline. Distinguish Walk, Board, Ride, Transfer, and Alight instructions. Emphasise MRT line code/name, bus service number, boarding point, destination stop, and verified station exit. Show travel direction, stop count, and platform only when available. Expand intermediate stops on demand. Keep estimated duration and arrival time at the top.
4. **Active journey:** show the current/next step prominently, with an explicit way to advance steps if location tracking is unavailable. For a disruption, explain which remaining leg is affected and show a proposed alternative with its duration difference. Let the commuter choose Use alternative before changing their displayed itinerary. Preserve the original route for comparison.
5. **Alerts:** replace repeated oversized Train Delay tiles with compact, actionable cards: affected line/service, location, impact, last updated, and next action. Prioritise My journey, with All services available separately. Include Weather and Accessibility categories when corresponding data is available. Distinguish no reported incidents from unavailable or stale data.

Use two bottom navigation destinations initially: **Plan** and **Alerts**. The active journey stays accessible from Plan. Add Saved only if saving trips is wanted; do not ship the wireframe's unnamed third tab.

## Standardised components — additional user reference

The user requested the supplied checkbox, icon-card, close-button, spinner, and alert-banner patterns. These are the component reference for implementation, alongside the original screen wireframes. The screenshot establishes anatomy and behaviour; it does not supply exact font, spacing, or colour tokens. Use consistent shared components and responsive sizing rather than reproducing the documentation panels or numbered anatomy markers.

- **Checkboxes:** a small rounded square with a purple checked state beside a visible, clickable label. Use for independent preferences such as Step-free route and for multi-select alert filters. Group related choices under a clear heading; place explanatory text beneath the label. Include unchecked, checked, focus, and disabled states. Use single-choice controls where only one selection is valid.
- **Icon cards:** follow the reference's icon, title, and short description anatomy for service/weather/accessibility summaries and alert categories. Maintain consistent padding, corner treatment, and alignment. Make a card interactive only when it opens details or performs an action, with keyboard access and a clear focus state. Keep direct actions such as Find route as labelled buttons.
- **Close buttons:** use the compact X control for dismissible panels, notices, and dialogs. Provide a descriptive accessible name, a generous invisible hit area, hover/focus/disabled states, and return focus to the opening control when appropriate. Closing details preserves the planned route and entered locations.
- **Loading indicators:** place the spinner and a short status label near the initiating action, for example Finding routes… or Updating service status…. Prevent duplicate submissions while loading, keep existing journey details readable during background refreshes, and announce status without repeatedly interrupting assistive technology. Honour reduced-motion preferences and provide a retry action after failure; never invent percentage progress for an unknown-duration request.
- **Announcement banner:** follow the compact dark strip with an icon, readable message, previous/next controls, and an item counter. The reference describes up to five items cycling every five seconds. For multiple general notices, provide pause/resume, pause on focus/hover, and disable automatic rotation for reduced motion. A single notice has no pagination. Let long messages wrap on mobile rather than hiding essential information.

Recommended adaptation for approval: keep urgent alerts affecting the current journey persistently visible next to that journey, with a clear View alternative action. General notices may rotate in the banner; urgent journey information should remain available without waiting for a carousel item. Dismissing a notice does not erase it from Alerts.

## Weather and service awareness

- Show weather relevant to the journey location and time, not just a generic temperature.
- When supported by data, describe the consequence: rain during an outdoor walking leg, an affected train segment, or an unavailable lift.
- A more sheltered recommendation must be backed by shelter/exposure data. Rain alone does not establish that another route is sheltered.
- Clearly label forecast, live status, scheduled information, and unavailable data. Display source/update information when supplied.
- Keep the itinerary readable if a feed or map fails. Never substitute an all-clear message for a failed request.

## Accessibility and interaction

- Aim for comfortably sized touch targets, readable text, strong contrast, keyboard navigation, visible focus, and screen-reader labels.
- Never make route meaning depend on colour or map access alone.
- Bottom panels need explicit expand/collapse controls as well as dragging.
- Preserve entered places and preferences when navigating back or retrying.
- Include loading, no matching address, no route, permission denied, offline, stale feed, and rerouting failure states.
- Only say Verified step-free when supported by the accessibility result; otherwise state which access information is unknown.

## Current implementation boundary

Repository inspection found a React/Vite/Leaflet frontend and API support for address lookup, one recommended route, departure date/time, step-free assessment, exit routing, train disruptions, and journey rerouting.

No weather endpoint or general bus operational-status endpoint was found in `backend/api/routes.py`. The route-leg response also does not explicitly provide structured platform, headsign, intermediate-stop list, or scheduled/live arrival fields. These details need API extensions or verified provider mappings before they can appear as real journey information.

The frontend can render available routing and disruption information now. Weather-aware ranking, reliable shelter comparisons, general bus incident monitoring, and richer transit instructions require additional data work. Any prototype examples for those states must be labelled as demonstration data.

## Approval scope

The supplied standardised component patterns are requested requirements. Approve or revise the proposed layout, timeline, two-tab navigation, conditions/alerts treatment (including persistent urgent alerts), and explicit reroute choice before frontend implementation begins. Weather and bus conditions remain part of the intended product; missing integrations must stay visible as incomplete work, not be presented as live features.

## Implementation notes

- The user approved the proposal and authorised direct implementation after the repository's BMad renderer was found to be missing.
- Implemented the responsive planner/map, Plan and Alerts navigation, location suggestions and geolocation, scheduling in Singapore time, shared component patterns, coloured itinerary, station exit details, a static route itinerary, service polling, and explicitly accepted alternatives.
- An alternative is calculated using a separate preview journey because the existing reroute endpoint changes server state. The displayed journey changes only after Use alternative. Alternatives do not inherit the original route's accessibility or station-exit verification.
- Journey guidance and manual progress controls were removed at the user’s request. Alerts monitor the planned route; rerouting uses its registered origin, not continuously tracked commuter progress.
- Weather and general bus operational feeds remain unconnected and are labelled unavailable. No sheltered-route ranking or live arrival claims are made. API responses currently provide one recommended route; alternative routes are requested when a disruption is detected.
- MRT colour families and line names follow the [LTA system map](https://www.lta.gov.sg/content/dam/ltagov/getting_around/public_transport/rail_network/pdf/SM_20250704_BI.pdf). App colour values are display choices rather than an assertion of official hexadecimal brand tokens.
- Browser tests use isolated API fixtures on desktop and mobile; they do not verify live provider accuracy or credentials.

## Latest screen behaviour

The user requested a single-screen initial planner with Find route visible and no initial map. The app shell now fits the viewport with fixed header/navigation. A successful Find route opens a separate map-and-itinerary screen; Edit trip preserves entered values. Long itineraries and exceptional expanded form states (scheduling, errors, very small viewports or enlarged text) can scroll within their panel so controls remain reachable.

The map title banner has been removed. The itinerary sheet follows pointer/touch dragging and snaps to 25%, 60%, or 85% of available screen height. Its handle stays visible while itinerary content scrolls independently. Tapping cycles positions; keyboard arrows, Home, and End offer equivalent controls.
