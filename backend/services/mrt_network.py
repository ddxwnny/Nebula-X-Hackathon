"""Canonical Singapore MRT network mapping, graph topology, and station code utilities."""

import re

# Canonical line station lists (for reference and validation)
LINE_STATION_SEQUENCES: dict[str, list[str]] = {
    "CCL": [
        "CC1", "CC2", "CC3", "CC4", "CC5", "CC6", "CC7", "CC8", "CC9", "CC10",
        "CC11", "CC12", "CC13", "CC14", "CC15", "CC16", "CC17", "CC19", "CC20",
        "CC21", "CC22", "CC23", "CC24", "CC25", "CC26", "CC27", "CC28", "CC29",
        "CE1", "CE2",
    ],
    "NSL": [
        "NS1", "NS2", "NS3", "NS4", "NS5", "NS7", "NS8", "NS9", "NS10",
        "NS11", "NS12", "NS13", "NS14", "NS15", "NS16", "NS17", "NS18", "NS19",
        "NS20", "NS21", "NS22", "NS23", "NS24", "NS25", "NS26", "NS27", "NS28",
    ],
    "EWL": [
        "EW1", "EW2", "EW3", "EW4", "EW5", "EW6", "EW7", "EW8", "EW9", "EW10",
        "EW11", "EW12", "EW13", "EW14", "EW15", "EW16", "EW17", "EW18", "EW19",
        "EW20", "EW21", "EW22", "EW23", "EW24", "EW25", "EW26", "EW27", "EW28",
        "EW29", "EW30", "EW31", "EW32", "EW33", "CG1", "CG2",
    ],
    "NEL": [
        "NE1", "NE3", "NE4", "NE5", "NE6", "NE7", "NE8", "NE9", "NE10",
        "NE11", "NE12", "NE13", "NE14", "NE15", "NE16", "NE17", "NE18",
    ],
    "DTL": [
        "DT1", "DT2", "DT3", "DT5", "DT6", "DT7", "DT8", "DT9", "DT10",
        "DT11", "DT12", "DT13", "DT14", "DT15", "DT16", "DT17", "DT18", "DT19",
        "DT20", "DT21", "DT22", "DT23", "DT24", "DT25", "DT26", "DT27", "DT28",
        "DT29", "DT30", "DT31", "DT32", "DT33", "DT34", "DT35",
    ],
    "TEL": [
        "TE1", "TE2", "TE3", "TE4", "TE5", "TE6", "TE7", "TE8", "TE9",
        "TE11", "TE12", "TE13", "TE14", "TE15", "TE16", "TE17", "TE18", "TE19",
        "TE20", "TE22", "TE25", "TE26", "TE27", "TE28", "TE29",
    ],
}

def _build_line_graphs() -> dict[str, dict[str, list[str]]]:
    """Construct exact topological adjacency graphs for each MRT line, handling branches."""
    graphs: dict[str, dict[str, list[str]]] = {}

    def add_edge(adj: dict[str, list[str]], u: str, v: str) -> None:
        adj.setdefault(u, []).append(v)
        adj.setdefault(v, []).append(u)

    def add_linear_chain(adj: dict[str, list[str]], chain: list[str]) -> None:
        for i in range(len(chain) - 1):
            add_edge(adj, chain[i], chain[i + 1])

    # 1. Circle Line (CCL): Main line CC1-CC29, branch from CC4 (Promenade) to CE1-CE2
    ccl_adj: dict[str, list[str]] = {}
    ccl_main = [
        "CC1", "CC2", "CC3", "CC4", "CC5", "CC6", "CC7", "CC8", "CC9", "CC10",
        "CC11", "CC12", "CC13", "CC14", "CC15", "CC16", "CC17", "CC19", "CC20",
        "CC21", "CC22", "CC23", "CC24", "CC25", "CC26", "CC27", "CC28", "CC29",
    ]
    add_linear_chain(ccl_adj, ccl_main)
    # Marina Bay branch connects at CC4 (Promenade)
    add_edge(ccl_adj, "CC4", "CE1")
    add_edge(ccl_adj, "CE1", "CE2")
    graphs["CCL"] = ccl_adj

    # 2. East-West Line (EWL): Main line EW1-EW33, branch from EW4 (Tanah Merah) to CG1-CG2
    ewl_adj: dict[str, list[str]] = {}
    ewl_main = [f"EW{i}" for i in range(1, 34)]
    add_linear_chain(ewl_adj, ewl_main)
    # Changi Airport branch connects at EW4 (Tanah Merah)
    add_edge(ewl_adj, "EW4", "CG1")
    add_edge(ewl_adj, "CG1", "CG2")
    graphs["EWL"] = ewl_adj

    # 3. North-South Line (NSL): Linear
    nsl_adj: dict[str, list[str]] = {}
    add_linear_chain(nsl_adj, LINE_STATION_SEQUENCES["NSL"])
    graphs["NSL"] = nsl_adj

    # 4. North East Line (NEL): Linear
    nel_adj: dict[str, list[str]] = {}
    add_linear_chain(nel_adj, LINE_STATION_SEQUENCES["NEL"])
    graphs["NEL"] = nel_adj

    # 5. Downtown Line (DTL): Linear
    dtl_adj: dict[str, list[str]] = {}
    add_linear_chain(dtl_adj, LINE_STATION_SEQUENCES["DTL"])
    graphs["DTL"] = dtl_adj

    # 6. Thomson-East Coast Line (TEL): Linear
    tel_adj: dict[str, list[str]] = {}
    add_linear_chain(tel_adj, LINE_STATION_SEQUENCES["TEL"])
    graphs["TEL"] = tel_adj

    return graphs

LINE_GRAPHS = _build_line_graphs()

LINE_NAME_ALIASES: dict[str, str] = {
    "CCL": "CCL",
    "CIRCLE": "CCL",
    "CIRCLE LINE": "CCL",
    "CC": "CCL",
    "NSL": "NSL",
    "NORTH SOUTH": "NSL",
    "NORTH SOUTH LINE": "NSL",
    "NORTH-SOUTH": "NSL",
    "NORTH-SOUTH LINE": "NSL",
    "NS": "NSL",
    "EWL": "EWL",
    "EAST WEST": "EWL",
    "EAST WEST LINE": "EWL",
    "EAST-WEST": "EWL",
    "EAST-WEST LINE": "EWL",
    "EW": "EWL",
    "NEL": "NEL",
    "NORTH EAST": "NEL",
    "NORTH EAST LINE": "NEL",
    "NORTH-EAST": "NEL",
    "NORTH-EAST LINE": "NEL",
    "NE": "NEL",
    "DTL": "DTL",
    "DOWNTOWN": "DTL",
    "DOWNTOWN LINE": "DTL",
    "DT": "DTL",
    "TEL": "TEL",
    "THOMSON EAST COAST": "TEL",
    "THOMSON EAST COAST LINE": "TEL",
    "THOMSON-EAST COAST": "TEL",
    "THOMSON-EAST COAST LINE": "TEL",
    "TE": "TEL",
}

STATION_NAME_TO_CODES: dict[str, list[str]] = {
    # CCL
    "DHOBY GHAUT": ["NS24", "NE6", "CC1"],
    "BRAS BASAH": ["CC2"],
    "ESPLANADE": ["CC3"],
    "PROMENADE": ["CC4", "DT15"],
    "NICOLL HIGHWAY": ["CC5"],
    "STADIUM": ["CC6"],
    "MOUNTBATTEN": ["CC7"],
    "DAKOTA": ["CC8"],
    "PAYA LEBAR": ["EW8", "CC9"],
    "MACPHERSON": ["CC10", "DT26"],
    "TAI SENG": ["CC11"],
    "BARTLEY": ["CC12"],
    "SERANGOON": ["NE12", "CC13"],
    "LORONG CHUAN": ["CC14"],
    "BISHAN": ["NS17", "CC15"],
    "MARYMOUNT": ["CC16"],
    "CALDECOTT": ["CC17", "TE9"],
    "BOTANIC GARDENS": ["CC19", "DT9"],
    "FARRER ROAD": ["CC20"],
    "HOLLAND VILLAGE": ["CC21"],
    "BUONA VISTA": ["EW21", "CC22"],
    "ONE-NORTH": ["CC23"],
    "KENT RIDGE": ["CC24"],
    "HAW PAR VILLA": ["CC25"],
    "PASIR PANJANG": ["CC26"],
    "LABRADOR PARK": ["CC27"],
    "TELOK BLANGAH": ["CC28"],
    "HARBOURFRONT": ["NE1", "CC29"],
    "BAYFRONT": ["CE1", "DT16"],
    "MARINA BAY": ["NS27", "CE2", "TE20"],

    # EWL
    "PASIR RIS": ["EW1"],
    "TAMPINES": ["EW2", "DT32"],
    "SIMEI": ["EW3"],
    "TANAH MERAH": ["EW4"],
    "BEDOK": ["EW5"],
    "KEMBANGAN": ["EW6"],
    "EUNOS": ["EW7"],
    "ALJUNIED": ["EW9"],
    "KALLANG": ["EW10"],
    "LAVENDER": ["EW11"],
    "BUGIS": ["EW12", "DT14"],
    "CITY HALL": ["NS25", "EW13"],
    "RAFFLES PLACE": ["NS26", "EW14"],
    "TANJONG PAGAR": ["EW15"],
    "OUTRAM PARK": ["EW16", "NE3", "TE17"],
    "TIONG BAHRU": ["EW17"],
    "REDHILL": ["EW18"],
    "QUEENSTOWN": ["EW19"],
    "COMMONWEALTH": ["EW20"],
    "DOVER": ["EW22"],
    "CLEMENTI": ["EW23"],
    "JURONG EAST": ["NS1", "EW24"],
    "CHINESE GARDEN": ["EW25"],
    "LAKESIDE": ["EW26"],
    "BOON LAY": ["EW27"],
    "PIONEER": ["EW28"],
    "JOO KOON": ["EW29"],
    "GUL CIRCLE": ["EW30"],
    "TUAS CRESCENT": ["EW31"],
    "TUAS WEST ROAD": ["EW32"],
    "TUAS LINK": ["EW33"],
    "EXPO": ["CG1", "DT35"],
    "CHANGI AIRPORT": ["CG2"],

    # NSL
    "BUKIT BATOK": ["NS2"],
    "BUKIT GOMBAK": ["NS3"],
    "CHOA CHU KANG": ["NS4"],
    "YEW TEE": ["NS5"],
    "KRANJI": ["NS7"],
    "MARSILING": ["NS8"],
    "WOODLANDS": ["NS9", "TE2"],
    "ADMIRALTY": ["NS10"],
    "SEMBAWANG": ["NS11"],
    "CANBERRA": ["NS12"],
    "YISHUN": ["NS13"],
    "KHATIB": ["NS14"],
    "YIO CHU KANG": ["NS15"],
    "ANG MO KIO": ["NS16"],
    "BRADDELL": ["NS18"],
    "TOA PAYOH": ["NS19"],
    "NOVENA": ["NS20"],
    "NEWTON": ["NS21", "DT11"],
    "ORCHARD": ["NS22", "TE14"],
    "SOMERSET": ["NS23"],
    "MARINA SOUTH PIER": ["NS28"],

    # NEL
    "CHINATOWN": ["NE4", "DT19"],
    "CLARKE QUAY": ["NE5"],
    "LITTLE INDIA": ["NE7", "DT12"],
    "FARRER PARK": ["NE8"],
    "BOON KENG": ["NE9"],
    "POTONG PASIR": ["NE10"],
    "WOODLEIGH": ["NE11"],
    "KOVAN": ["NE13"],
    "HOUGANG": ["NE14"],
    "BUANGKOK": ["NE15"],
    "SENGKANG": ["NE16"],
    "PUNGGOL": ["NE17"],
}


def normalize_line_name(line: str | None) -> str | None:
    if not line:
        return None
    cleaned = line.strip().upper()
    return LINE_NAME_ALIASES.get(cleaned, cleaned)


def _clean_station_name(name: str) -> str:
    cleaned = name.upper()
    for suffix in [" MRT STATION", " STN", " STATION", " MRT"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
    return cleaned


def extract_station_code(text: str) -> str | None:
    """Extract code like CC10, NS24, EW8, DT15 from string if present."""
    match = re.search(r"\b([A-Z]{1,3}\d{1,3})\b", text.upper())
    return match.group(1) if match else None


def station_code_for_name(station_name: str, line: str | None = None) -> str | None:
    extracted = extract_station_code(station_name)
    if extracted:
        return extracted

    cleaned = _clean_station_name(station_name)
    codes = STATION_NAME_TO_CODES.get(cleaned, [])
    if not codes:
        return None

    if not line:
        return codes[0]

    canon_line = normalize_line_name(line)
    prefix_map = {
        "CCL": ("CC", "CE"),
        "NSL": ("NS",),
        "EWL": ("EW", "CG"),
        "NEL": ("NE",),
        "DTL": ("DT",),
        "TEL": ("TE",),
    }
    allowed_prefixes = prefix_map.get(canon_line, (canon_line,))
    for code in codes:
        if any(code.startswith(pref) for pref in allowed_prefixes):
            return code
    return codes[0]


def _bfs_shortest_path(adj: dict[str, list[str]], start: str, end: str) -> list[str]:
    """Find topological station path in the MRT line graph."""
    if start == end:
        return [start]
    queue: list[list[str]] = [[start]]
    visited = {start}
    while queue:
        path = queue.pop(0)
        node = path[-1]
        for neighbor in adj.get(node, []):
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return [start, end]


def get_stations_traversed(line: str | None, from_station: str, to_station: str) -> list[str]:
    """Return all station codes along the line between from_station and to_station (inclusive)."""
    canon_line = normalize_line_name(line)
    from_code = station_code_for_name(from_station, canon_line)
    to_code = station_code_for_name(to_station, canon_line)

    if not from_code or not to_code:
        return [c for c in [from_code, to_code] if c]

    if canon_line in LINE_GRAPHS:
        return _bfs_shortest_path(LINE_GRAPHS[canon_line], from_code, to_code)

    return [from_code, to_code]


def check_station_overlap(journey_stations: list[str], disrupted_stations: list[str]) -> list[str]:
    """Find overlapping station codes between journey and disrupted segments."""
    j_set = {s.strip().upper() for s in journey_stations if s.strip()}
    d_set = {s.strip().upper() for s in disrupted_stations if s.strip()}
    return sorted(j_set.intersection(d_set))
