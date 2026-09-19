import { test, expect } from "@playwright/test";

const walk = {
  mode: "walk",
  duration_min: 5,
  distance_m: 350,
  from: "Home",
  to: "Bedok",
  geometry: [
    { lat: 1.325, lon: 103.93 },
    { lat: 1.324, lon: 103.929 },
  ],
};
const train = {
  mode: "mrt",
  duration_min: 20,
  line_name: "East West Line",
  from: "Bedok",
  to: "Kallang",
  geometry: [
    { lat: 1.324, lon: 103.929 },
    { lat: 1.311, lon: 103.871 },
  ],
};
const planned = {
  request_id: "test-route",
  origin: { lat: 1.325, lon: 103.93, label: "Home" },
  destination: { lat: 1.311, lon: 103.871, label: "Kallang" },
  recommended_route: {
    total_duration_min: 25,
    legs: [walk, train],
    exit_routing: {
      enabled: true,
      fallback_to_station_centroid: false,
      origin: { station_name: "Bedok", exit_name: "Exit A" },
    },
  },
  accessibility: {
    step_free: true,
    accessible: false,
    verification: "unknown",
    lifts_used: [],
    unknown_segments: 1,
  },
  decision: {
    summary: "One walking connection has unverified access.",
    details: [],
  },
};
const network = {
  status: 2,
  data_status: "ok",
  timestamp: new Date().toISOString(),
  affected_segments: [{ line: "EW", stations: ["Bedok", "Kallang"] }],
  messages: [
    "East West Line: allow additional travel time.",
    "Check station announcements for updates.",
  ],
};
const disruption = { line: "EW", affected_stations: ["Bedok", "Kallang"] };
const alternative = {
  status: "rerouted",
  previous_route: { remaining_duration_min: 25 },
  new_route: {
    remaining_duration_min: 30,
    legs: [{ ...train, mode: "bus", line_name: "100", from: "Home" }],
  },
  change: {
    additional_duration_min: 5,
    reason: "Avoids the affected train section.",
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (request) => {
    const path = new URL(request.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/disruptions/status")) body = network;
    else if (path.includes("/locations/search"))
      body = [{ address: "Bedok", lat: 1.324, lon: 103.929 }];
    else if (path.endsWith("/routes/plan")) body = planned;
    else if (path.endsWith("/journeys")) body = { journey_id: "test-journey" };
    else if (path.endsWith("/status"))
      body = { status: "reroute_required", data_status: "ok", disruption };
    else if (path.endsWith("/reroute")) body = alternative;
    await request.fulfill({ json: body });
  });
  // These fixtures verify interaction without depending on map or font networks.
  await page.route("https://*.tile.openstreetmap.org/**", (request) =>
    request.abort(),
  );
  await page.route("https://fonts.googleapis.com/**", (request) =>
    request.abort(),
  );
  await page.goto("/");
});
async function plan(page: import("@playwright/test").Page) {
  await page.getByLabel("From", { exact: true }).fill("Home");
  await page.getByLabel("To", { exact: true }).fill("Kallang");
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Journey results" }),
  ).toBeVisible();
}

test("planner, alerts and layout remain usable at both screen sizes", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "Where to today?" }),
  ).toBeVisible();
  await expect(
    page.getByText("Weather updates unavailable", { exact: true }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Alerts" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Travel updates." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "All services", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "EW · Service disruption" }),
  ).toBeVisible();
  await page.getByLabel("Train", { exact: true }).uncheck();
  await expect(
    page.getByRole("heading", { name: "EW · Service disruption" }),
  ).not.toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Plan", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Where to today?" }),
  ).toBeVisible();
});

test("route details and accessibility remain without unsupported guidance", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await plan(page);
  await expect(
    page.getByText("Step-free access not fully verified"),
  ).toBeVisible();
  await expect(
    page.getByText("EW · East West Line", { exact: true }),
  ).toBeVisible();
  await page.getByText("Station entrances & exits", { exact: true }).click();
  await expect(page.getByText("Exit A", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Hide journey details" }).click();
  await expect(
    page.getByRole("heading", { name: "Route details" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Show journey details" }).click();
  await expect(page.getByRole("button", { name: "Start journey" })).toHaveCount(
    0,
  );
  await expect(page.getByText("Your journey, mapped out")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("alternative does not replace the route until explicitly accepted", async ({
  page,
}) => {
  await plan(page);
  await page.getByRole("button", { name: "View alternative" }).click();
  await expect(
    page.getByRole("button", { name: "Use alternative" }),
  ).toBeVisible();
  const timeline = page.locator(".timeline");
  await expect(timeline.getByText("EW · East West Line")).toBeVisible();
  await expect(timeline.getByText("Bus 100")).not.toBeVisible();
  await page.getByRole("button", { name: "Keep current" }).click();
  await expect(timeline.getByText("EW · East West Line")).toBeVisible();
  await page.getByRole("button", { name: "View alternative" }).click();
  await page.getByRole("button", { name: "Use alternative" }).click();
  await expect(timeline.getByText("Bus 100")).toBeVisible();
  await expect(
    page.getByText(
      "Accessibility and exit details are unverified for this alternative.",
    ),
  ).toBeVisible();
  await expect(page.getByText("Station entrances & exits")).not.toBeVisible();
  await page.getByRole("button", { name: /Compare original route/ }).click();
  await expect(timeline.getByText("EW · East West Line")).toBeVisible();
});

test("failed planning preserves the previous route and input", async ({
  page,
}) => {
  await plan(page);
  await page.getByRole("button", { name: "Edit trip" }).click();
  await page.route("**/routes/plan", (route) =>
    route.fulfill({ status: 503, json: { detail: "Unavailable" } }),
  );
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  await expect(
    page.getByText(
      "Journey information is temporarily unavailable. Please try again shortly.",
    ),
  ).toBeVisible();
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("Home");
  await page.getByRole("button", { name: "Return to current route" }).click();
  await expect(
    page.locator(".timeline").getByText("EW · East West Line"),
  ).toBeVisible();
});

test("failed service feed does not claim services are running normally", async ({
  page,
}) => {
  await page.route("**/disruptions/status", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.reload();
  await expect(
    page.getByText("Service status unavailable", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No train disruptions reported"),
  ).not.toBeVisible();
});

test("location denial and reroute failure have recoverable states", async ({
  page,
}) => {
  await page.evaluate(() => {
    navigator.geolocation.getCurrentPosition = (_success, error) =>
      error?.({
        code: 1,
        message: "Denied",
        PERMISSION_DENIED: 1,
        POSITION_UNAVAILABLE: 2,
        TIMEOUT: 3,
      });
  });
  await page.getByRole("button", { name: "Use my location" }).click();
  await expect(
    page.getByText(
      "We couldn’t access your location. Enter your starting point instead.",
    ),
  ).toBeVisible();
  await plan(page);
  await page.route("**/reroute", (route) =>
    route.fulfill({ status: 502, json: {} }),
  );
  await page.getByRole("button", { name: "View alternative" }).click();
  await expect(
    page.getByText("We couldn’t complete this request. Please try again."),
  ).toBeVisible();
  await expect(
    page.locator(".timeline").getByText("EW · East West Line"),
  ).toBeVisible();
});

test("departure scheduling and swapping preserve the submitted places", async ({
  page,
}) => {
  await page.getByLabel("From", { exact: true }).fill("Home");
  await page.getByLabel("To", { exact: true }).fill("Kallang");
  await page
    .getByRole("button", { name: "Swap origin and destination" })
    .click();
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("Kallang");
  await page.getByLabel("Departure", { exact: true }).selectOption("later");
  await page.getByLabel("Date", { exact: true }).fill("2030-01-02");
  await page.getByLabel("Time (SGT)", { exact: true }).fill("09:30");
  await page.getByText("Step-free route", { exact: true }).click();
  const request = page.waitForRequest("**/routes/plan");
  await page.getByRole("button", { name: "Find route", exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({
    origin: { address: "Kallang" },
    destination: { address: "Home" },
    departure_date: "2030-01-02",
    departure_time: "09:30",
    preferences: { stepFree: true },
  });
});

test("sheet resizes by tap, keyboard and drag while retaining map and route", async ({
  page,
}) => {
  await plan(page);
  const handle = page.getByRole("slider", { name: "Journey panel size" });
  const map = page.getByRole("region", { name: "Journey map" });
  await expect(handle).toHaveAttribute("aria-valuenow", "60");
  const initialMap = (await map.boundingBox())!.height;
  await handle.click();
  await expect(handle).toHaveAttribute("aria-valuenow", "85");
  expect((await map.boundingBox())!.height).toBeLessThan(initialMap);
  await handle.press("Home");
  await expect(handle).toHaveAttribute("aria-valuenow", "25");
  expect((await map.boundingBox())!.height).toBeGreaterThan(initialMap);
  await handle.press("ArrowUp");
  await expect(handle).toHaveAttribute("aria-valuenow", "60");
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y - 120, { steps: 8 });
  expect(Number(await handle.getAttribute("aria-valuenow"))).toBeGreaterThan(
    60,
  );
  await page.mouse.up();
  await expect(handle).toHaveAttribute("aria-valuenow", "85");
  const expanded = (await handle.boundingBox())!;
  await page.mouse.move(expanded.x + 40, expanded.y + 20);
  await page.mouse.down();
  await page.mouse.move(expanded.x + 40, expanded.y + 440, { steps: 12 });
  await page.mouse.up();
  await expect(handle).toHaveAttribute("aria-valuenow", "25");
  await expect(page.locator(".leaflet-container")).toBeVisible();
  await page.locator(".sheet-content").evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(handle).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollHeight <= innerHeight,
    ),
  ).toBe(true);
});

test("initial planner fits one screen and mounts the map only after planning", async ({
  page,
}) => {
  for (const height of [844, 667]) {
    await page.setViewportSize({ width: 390, height });
    await expect(page.locator(".leaflet-container")).toHaveCount(0);
    const button = await page
      .getByRole("button", { name: "Find route", exact: true })
      .boundingBox();
    const navigation = await page.getByRole("navigation").boundingBox();
    expect(button!.y + button!.height).toBeLessThanOrEqual(navigation!.y);
    expect(
      await page
        .locator(".planner-panel")
        .evaluate((el) => el.scrollHeight <= el.clientHeight),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
  }
  await plan(page);
  await expect(page.locator(".leaflet-container")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Where to today?" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Edit trip" }).click();
  await expect(page.locator(".leaflet-container")).toHaveCount(0);
  await expect(page.getByLabel("From", { exact: true })).toHaveValue("Home");
});
