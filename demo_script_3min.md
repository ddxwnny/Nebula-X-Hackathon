# sMaRT Move - 3-Minute Demo Video Script

**Format:** Screen recording with voiceover
**Audience:** Hackathon judges
**Persona:** Jane Koh Swee Hoon, a motorized wheelchair commuter
**Framework:** Pitch Narrative / Customer Journey
**Target length:** 3 minutes

## 0:00-0:15 - Hook

**Screen:** Show the app landing screen. Keep the map and planner visible.

**Voiceover:**

"For Jane, a broken MRT lift is not a five-minute inconvenience. It can make an entire journey impossible. sMaRT Move is built around a simple promise: do not just tell her that something changed. Tell her whether she can still complete the journey, and what to do next."

## 0:15-0:35 - Set Up Jane's Journey

**Screen:** In the planner, enter:

- From: `Ang Mo Kio MRT Station`
- To: `Singapore General Hospital`
- Enable `Step-free route`
- Click `Find route`

**Voiceover:**

"We are planning Jane's trip from Ang Mo Kio MRT Station to Singapore General Hospital. The important detail is the step-free preference. The app treats lifts, ramps, station exits, and the walking legs as part of one journey, instead of assuming that every commuter can use the same path."

## 0:35-1:05 - Show the Route Decision

**Screen:** Let the route load. Show the journey map, route badges, duration, arrival estimate, and route details.

**Voiceover:**

"The result is door to door: walking, rail, bus, and walking again. The route summary tells Jane how long the journey takes and when she should arrive. The timeline explains where to board, where to alight, and how long each section takes."

"Below that, the app states whether step-free access is verified. If a lift or exit cannot be confirmed, it says so plainly instead of giving false reassurance."

## 1:05-1:30 - Show the Physical World

**Screen:** Pan or zoom the map. Point to the OSM-backed map, covered walkway overlay, and station ground-level polygons. Open the station exit details.

**Voiceover:**

"This is where sMaRT Move goes beyond a station-to-station planner. The map combines OpenStreetMap with official transport layers. Covered walkways appear along the route, station footprints show underground or elevated transitions, and station exit information tells Jane where to enter and leave."

"Every map view carries OpenStreetMap attribution, and the map uses a compliant tile provider rather than hammering public OSM tiles."

## 1:30-1:50 - Crowd and Weather Decisions

**Screen:** Show the weather, crowd-control, and bus information in the journey details. If live data is unavailable, show the explicit unavailable state rather than inventing a result.

**Voiceover:**

"The app also checks conditions that change the experience of an accessible journey. Crowd Control combines live and forecast MRT crowd levels and explains the trade-off: a calmer boarding window may mean extra waiting, but less platform and lift congestion. Weather guidance identifies rain along the route, while bus legs can show live arrivals and vehicle accessibility."

## 1:50-2:10 - Move to Alerts

**Screen:** Click the alerts bell, then select `All services` if needed. Show the train service status and affected segments.

**Voiceover:**

"Now we move from planning to monitoring. sMaRT Move keeps checking the official train service feed. Jane does not need to interpret a generic network alert. The app compares the disruption with her active journey and tells her when her route is affected."

## 2:10-2:35 - Compare an Alternative

**Screen:** With a disruption visible on the active line, return to the journey and click `View alternative`. Show the original route and proposed alternative, including the duration difference and explanation.

**Voiceover:**

"When the route is affected, Jane gets a decision, not just a warning. She can view an alternative, see the additional travel time, understand which disrupted section is being avoided, and keep the original route if it is still the better choice. The alternative does not silently replace her current plan."

## 2:35-2:50 - Confirm the New Journey

**Screen:** Click `Use alternative`. Show the updated route timeline and map.

**Voiceover:**

"Only after Jane chooses it does the app update the journey. The new route is visible on the map and in the timeline, with the trade-off stated in plain language. That preserves control for the commuter instead of making an opaque decision on her behalf."

## 2:50-3:00 - Close

**Screen:** Return to the route summary. Hold on the accessibility decision and arrival estimate.

**Voiceover:**

"Most journey planners optimize for speed. sMaRT Move optimizes for a journey Jane can actually finish. It combines live disruptions, accessibility constraints, geospatial reality, crowding, weather, and clear alternatives in one place. That is the difference between knowing that the network changed and knowing what to do next."

## Recording Notes

- Record at phone width or in a phone-sized browser window.
- Keep the cursor visible only when selecting a control.
- Pause briefly after each result appears so judges can read the decision.
- Use the disruption replay or mocked alert fixture if the live train feed is quiet during recording.
- Do not claim measured accuracy, guaranteed accessibility, or actual staff dispatch; the prototype reports the limits of its source data.
