import html
import sys
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlunparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HOMEPAGE_URL = "https://all.accor.com"
OUTPUT_FILE = Path("final_api_response.html")
PAGE_SIZE = 100
MAX_PAGES = 40
TIMEOUT = 30

REQUIRED_HOTEL_FIELDS = [
    "id",
    "name",
    "brand",
    "stars",
    "status",
    "city",
    "country",
    "countryCode",
    "street",
    "zipCode",
    "lat",
    "lng",
    "factsheetUrl",
]
OPTIONAL_HOTEL_FIELDS = ["rating", "reviewCount", "region", "image"]

PLACE_HIGHLIGHT = {
    "all": ["name", "alternate_names", "city_trad", "country_translated", "country_trad", "label_en"],
    "city": ["name", "alternate_names", "city_trad"],
    "country": ["name", "country_translated", "country_trad"],
    "label": ["name", "alternate_names", "label_en"],
}


def decode_html(value):
    return html.unescape(value)


def score_endpoint(url):
    lower = url.lower()
    if re.search(r"\.(?:js|css|png|jpe?g|svg|webp|gif|woff2?)(?:\?|$)", lower):
        return -1
    if "/api/rest/v1/hotels" in lower:
        return -1
    if "ahstatic.com" in lower or "/is/image/" in lower:
        return -1

    score = 0
    if "api" in lower:
        score += 2
    if "rest" in lower:
        score += 1
    if re.search(r"/v\d+/", lower):
        score += 3
    if "hotels" in lower:
        score += 5
    if "search" in lower:
        score += 2
    if "catalog" in lower:
        score += 3
    if lower.startswith("http"):
        score += 1
    if ".html" in lower or "destination/" in lower:
        score -= 6
    return score


def find_endpoints(page_html, base_url):
    text = decode_html(page_html)
    found = {}
    for match in re.finditer(r"https?://[^\s\"'<>\\]+|/api/[^\s\"'<>\\]+", text, re.I):
        raw = re.sub(r"[,);]+$", "", match.group(0))
        try:
            absolute = urljoin(base_url, raw)
        except ValueError:
            continue
        score = score_endpoint(absolute)
        if score < 4:
            continue
        previous = found.get(absolute)
        if previous is None or score > previous["score"]:
            found[absolute] = {"url": absolute, "score": score}
    return sorted(found.values(), key=lambda item: (-item["score"], len(item["url"])))


def build_catalog_request_url(endpoint, place_query="paris"):
    parts = urlparse(endpoint)
    if "/catalog/v1/hotels" not in parts.path:
        return endpoint
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("q", place_query)
    query.setdefault("fields", "place.searchBox")
    return urlunparse(parts._replace(query=urlencode(query)))


def read_json_attribute(page_html, name):
    text = decode_html(page_html)
    match = re.search(re.escape(name) + r"='(\{[\s\S]*?\})'", text)
    if not match:
        return None
    return json.loads(match.group(1))


def plain(value):
    normalized = unicodedata.normalize("NFD", str(value))
    stripped = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return stripped.lower()


def highlight_list(hit, field):
    highlights = (hit or {}).get("_highlightResult") or {}
    value = highlights.get(field)
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def highlight_score(hit, fields):
    if not hit or not hit.get("_highlightResult"):
        return 0
    score = 0
    for field in fields:
        for item in highlight_list(hit, field):
            if item and item.get("matchLevel") != "none" and isinstance(item.get("matchedWords"), list):
                score = max(score, len(item["matchedWords"]))
    return score


def matched_words(hit):
    words = set()
    highlights = (hit or {}).get("_highlightResult") or {}
    for field in highlights:
        for item in highlight_list(hit, field):
            if item and item.get("matchLevel") != "none" and isinstance(item.get("matchedWords"), list):
                words.update(str(word).lower() for word in item["matchedWords"])
    return list(words)


def place_record(hit):
    geoloc = (hit or {}).get("_geoloc") or {}
    try:
        lat = float(geoloc.get("lat"))
    except (TypeError, ValueError):
        return None
    if lat != lat:
        return None
    city = hit.get("capitale") if hit.get("type") in (1, 3) else hit.get("name")
    if not city or not hit.get("cou_name_en"):
        return None
    return {
        "city": city,
        "country": hit["cou_name_en"],
        "type": hit.get("type"),
        "coordinates": geoloc,
    }


def choose_place(results, query):
    if not results or len(results) < 5:
        return None
    hits = [(result.get("hits") or [None])[0] if result.get("hits") else None for result in results]
    scores = [
        highlight_score(hits[0], PLACE_HIGHLIGHT["all"]),
        highlight_score(hits[1], PLACE_HIGHLIGHT["all"]),
        highlight_score(hits[2], PLACE_HIGHLIGHT["city"]),
        highlight_score(hits[3], PLACE_HIGHLIGHT["country"]),
        highlight_score(hits[4], PLACE_HIGHLIGHT["label"]),
    ]
    best_typed = max(scores[2], scores[3], scores[4])
    hit = None
    if scores[0] > 0:
        hit = hits[0]
    elif scores[1] > 0 and scores[1] >= best_typed:
        hit = hits[1]
    elif results[3].get("nbHits") == 1 and scores[3] > 0:
        hit = hits[3]
    elif best_typed > 0:
        ranked = [
            item
            for item in (
                {"priority": 1, "score": scores[2], "hit": hits[2]},
                {"priority": 2, "score": scores[4], "hit": hits[4]},
                {"priority": 3, "score": scores[3], "hit": hits[3]},
            )
            if item["score"] > 0 and item["hit"]
        ]
        ranked.sort(key=lambda item: (-item["score"], item["priority"]))
        hit = ranked[0]["hit"] if ranked else None
    place = place_record(hit)
    if not place or not hit:
        return None
    skip = {plain(word) for word in matched_words(hit)}
    remaining = " ".join(word for word in query.split() if plain(word) not in skip).strip()
    if place["type"] in (1, 3):
        geo_query = place["country"].lower()
    else:
        geo_query = f"{place['city']}, {place['country']}".lower()
    return {"place": place, "geoQuery": geo_query, "remainingQuery": remaining}


def place_queries(index_name, query):
    return [
        {
            "indexName": index_name,
            "query": query,
            "analytics": False,
            "hitsPerPage": 1,
            "removeStopWords": False,
            "attributesToHighlight": PLACE_HIGHLIGHT["all"],
        },
        {
            "indexName": index_name,
            "query": query,
            "analytics": False,
            "hitsPerPage": 1,
            "attributesToHighlight": PLACE_HIGHLIGHT["all"],
        },
        {
            "indexName": index_name,
            "query": query,
            "filters": "type:0",
            "analytics": False,
            "hitsPerPage": 1,
            "attributesToHighlight": PLACE_HIGHLIGHT["city"],
        },
        {
            "indexName": index_name,
            "query": query,
            "filters": "type:1 OR type:3",
            "analytics": False,
            "hitsPerPage": 1,
            "attributesToHighlight": PLACE_HIGHLIGHT["country"],
        },
        {
            "indexName": index_name,
            "query": query,
            "filters": "type:2",
            "analytics": False,
            "hitsPerPage": 1,
            "attributesToHighlight": PLACE_HIGHLIGHT["label"],
        },
    ]


def sanitized_algolia_url(url):
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "x-algolia-api-key" in query:
        query["x-algolia-api-key"] = "[redacted]"
    return urlunparse(parts._replace(query=urlencode(query)))


def algolia_search(session, app_id, api_key, search_requests):
    url = f"https://{app_id}-dsn.algolia.net/1/indexes/*/queries"
    params = {"x-algolia-application-id": app_id, "x-algolia-api-key": api_key}
    full_url = f"{url}?{urlencode(params)}"
    print("request: POST", sanitized_algolia_url(full_url))
    response = session.post(
        url,
        params=params,
        data=json.dumps({"requests": search_requests}),
        headers={
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "Referer": "https://all.accor.com/",
        },
        timeout=TIMEOUT,
    )
    print("status:", response.status_code)
    print("content-type:", response.headers.get("content-type") or "(none)")
    try:
        data = response.json()
    except ValueError:
        data = None
    return {"status": response.status_code, "data": data}


def search_box_values(body):
    data = json.loads(body)
    box = (data.get("place") or {}).get("searchBox")
    if not box or not box.get("topRight") or not box.get("bottomLeft"):
        return None
    values = [
        float(box["topRight"]["lat"]),
        float(box["topRight"]["lng"]),
        float(box["bottomLeft"]["lat"]),
        float(box["bottomLeft"]["lng"]),
    ]
    if any(value != value for value in values):
        return None
    return {"box": box, "values": values}


def find_api_key_near(page_html, endpoint):
    text = decode_html(page_html)
    index = text.find(endpoint)
    if index == -1:
        return None
    before = text[max(0, index - 800) : index]
    matches = list(re.finditer(r"api[-_]?key[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_-]+)[\"']", before, re.I))
    if not matches:
        return None
    return matches[-1].group(1)


def cookie_names(session, url):
    names = []
    for cookie in session.cookies:
        if cookie.domain and cookie.domain.lstrip(".") not in urlparse(url).hostname:
            continue
        names.append(cookie.name)
    return names


def get_page(session, url, extra_headers=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if extra_headers:
        headers.update(extra_headers)
    names = cookie_names(session, url)
    print("request: GET", url)
    print("cookie names:", ", ".join(names) or "(none)")
    print("Apikey present:", bool(headers.get("Apikey") or headers.get("apikey")))
    response = session.get(url, headers=headers, timeout=TIMEOUT)
    print("url:", response.url)
    print("status:", response.status_code)
    return response


def text(value):
    return "" if value is None else str(value).strip()


def finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    if number.is_integer():
        return int(number)
    return number


def labels(items):
    if not isinstance(items, list):
        return []
    values = []
    for item in items:
        if isinstance(item, dict):
            values.append(text(item.get("label") or item.get("name") or item.get("code")))
        else:
            values.append(text(item))
    return [value for value in values if value]


def normalize_hotel(hit):
    localization = (hit or {}).get("localization") or {}
    address = localization.get("address") or {}
    gps = localization.get("gps") or {}
    rating = (hit or {}).get("rating") or {}
    medias = (hit or {}).get("medias") or {}
    return {
        "id": text((hit or {}).get("objectID")),
        "name": text((hit or {}).get("name")),
        "brand": text((hit or {}).get("brandLabel") or (hit or {}).get("brand")),
        "chain": text((hit or {}).get("chainLabel") or (hit or {}).get("chain")),
        "stars": finite_number((hit or {}).get("stars")),
        "rating": finite_number(rating.get("score")),
        "reviewCount": finite_number(rating.get("nbReviews")),
        "status": text((hit or {}).get("status")),
        "description": text((hit or {}).get("description")),
        "lodging": text((hit or {}).get("lodging")),
        "city": text((hit or {}).get("city") or address.get("city")),
        "region": text((hit or {}).get("region")),
        "country": text((hit or {}).get("country") or address.get("country")),
        "countryCode": text(address.get("countryCode")),
        "continent": text((hit or {}).get("continent") or address.get("continent")),
        "street": text(address.get("street") or address.get("line1")),
        "zipCode": text(address.get("zipCode")),
        "lat": finite_number(gps.get("lat")),
        "lng": finite_number(gps.get("lng")),
        "factsheetUrl": text((hit or {}).get("factsheetUrl")),
        "image": text(medias.get("dmUrlCrop3by2")),
        "amenities": labels((hit or {}).get("freeAmenities")),
    }


def missing_value(value):
    return value is None or value == "" or value == []


def count_missing(hotels, fields):
    missing = {}
    for field in fields:
        count = sum(1 for hotel in hotels if missing_value(hotel.get(field)))
        if count:
            missing[field] = count
    return missing


def field_coverage(hotels):
    missing = count_missing(hotels, REQUIRED_HOTEL_FIELDS)
    optional_missing = count_missing(hotels, OPTIONAL_HOTEL_FIELDS)
    complete = sum(
        1 for hotel in hotels if all(not missing_value(hotel.get(field)) for field in REQUIRED_HOTEL_FIELDS)
    )
    return {
        "required": REQUIRED_HOTEL_FIELDS,
        "optional": OPTIONAL_HOTEL_FIELDS,
        "completeRecords": complete,
        "incompleteRecords": len(hotels) - complete,
        "missing": missing,
        "optionalMissing": optional_missing,
        "fullFields": bool(hotels) and complete == len(hotels),
    }


def empty_result(destination, place=None, geo_query=""):
    return {
        "query": destination,
        "place": place,
        "geoQuery": geo_query,
        "nbHits": 0,
        "pagesFetched": 0,
        "paginationComplete": False,
        "fields": field_coverage([]),
        "hotels": [],
    }


def fetch_hotel_pages(session, app_id, api_key, request):
    hotels = []
    seen = set()
    page = 0
    nb_pages = 1
    nb_hits = 0
    while page < nb_pages and page < MAX_PAGES:
        response = algolia_search(
            session,
            app_id,
            api_key,
            [{**request, "page": page, "hitsPerPage": PAGE_SIZE}],
        )
        results = (response["data"] or {}).get("results") or []
        first = results[0] if results else None
        if not first:
            break
        nb_pages = int(first["nbPages"]) if isinstance(first.get("nbPages"), (int, float)) else 0
        nb_hits = int(first["nbHits"]) if isinstance(first.get("nbHits"), (int, float)) else len(hotels)
        hits = first.get("hits") or []
        if not hits:
            break
        for hit in hits:
            hotel = normalize_hotel(hit)
            if not hotel["id"] or hotel["id"] in seen:
                continue
            seen.add(hotel["id"])
            hotels.append(hotel)
        page += 1
    return {
        "hotels": hotels,
        "nbHits": nb_hits,
        "pagesFetched": page,
        "paginationComplete": hotels and len(hotels) >= nb_hits if nb_hits else page == 0 or not hotels,
    }


def search_destination(session, destination, app_id, algolia_key, places_index, hotels_index, catalog_endpoint, catalog_key):
    print(f"\n=== hotel search: {destination} ===")
    places = algolia_search(session, app_id, algolia_key, place_queries(places_index, destination))
    resolved = choose_place((places["data"] or {}).get("results"), destination) if places["data"] else None
    if not resolved:
        print("Resolved destination: (place lookup did not return a match)")
        print("Hotel records: 0")
        return empty_result(destination)

    print("Resolved destination:")
    print(json.dumps(resolved["place"]))
    print("geo query:", resolved["geoQuery"])
    print("remaining query:", resolved["remainingQuery"] or "(empty)")

    catalog_url = build_catalog_request_url(catalog_endpoint, resolved["geoQuery"])
    headers = {"Accept": "application/json", "Accept-Language": "en"}
    if catalog_key:
        headers["Apikey"] = catalog_key
    catalog = get_page(session, catalog_url, headers)
    try:
        located = search_box_values(catalog.text)
    except ValueError:
        located = None
    if not located:
        print("Hotel records: 0")
        return empty_result(destination, resolved["place"], resolved["geoQuery"])
    print("search box:", json.dumps(located["box"]))

    boxed_request = {
        "indexName": hotels_index,
        "query": resolved["remainingQuery"],
        "facets": [],
        "filters": "status:OPEN",
        "insideBoundingBox": [located["values"]],
    }
    fetched = fetch_hotel_pages(session, app_id, algolia_key, boxed_request)
    hotel_request = boxed_request
    if not fetched["hotels"]:
        print("bounding-box query hits:", 0)
        hotel_request = {
            "indexName": hotels_index,
            "query": destination,
            "facets": [],
            "filters": "status:OPEN",
        }
        fetched = fetch_hotel_pages(session, app_id, algolia_key, hotel_request)

    coverage = field_coverage(fetched["hotels"])
    print("Hotel endpoint:")
    print(f"POST https://{app_id}-dsn.algolia.net/1/indexes/*/queries")
    print("Hotel request:")
    print(json.dumps({**hotel_request, "page": 0, "hitsPerPage": PAGE_SIZE}))
    print("Hotel records:")
    print(len(fetched["hotels"]))
    print("reported nbHits:", fetched["nbHits"])
    print("pages fetched:", fetched["pagesFetched"])
    print("pagination complete:", fetched["paginationComplete"])
    print("full fields:", coverage["fullFields"])
    print("complete records:", f"{coverage['completeRecords']}/{len(fetched['hotels'])}")
    if not coverage["fullFields"]:
        print("required fields still empty:", json.dumps(coverage["missing"]))
    if coverage["optionalMissing"]:
        print("optional fields empty on some records:", json.dumps(coverage["optionalMissing"]))
    print("First 5 hotels:")
    for index, hotel in enumerate(fetched["hotels"][:5], start=1):
        print(f"{index}. {hotel['id']} {hotel['name']} | {hotel['brand']} | {hotel['city']}, {hotel['country']}")

    return {
        "query": destination,
        "place": resolved["place"],
        "geoQuery": resolved["geoQuery"],
        "nbHits": fetched["nbHits"],
        "pagesFetched": fetched["pagesFetched"],
        "paginationComplete": fetched["paginationComplete"],
        "fields": coverage,
        "hotels": fetched["hotels"],
    }


def parse_catalog(body):
    try:
        data = json.loads(body)
    except ValueError:
        return {"validJson": False, "place": None, "hotels": []}
    rows = data.get("hotels") if isinstance(data.get("hotels"), list) else data.get("results") or []
    if not isinstance(rows, list):
        rows = []
    hotels = []
    for row in rows:
        hotel_id = text(row.get("id") or row.get("hotelId") or row.get("code"))
        name = text(row.get("name") or row.get("hotelName"))
        if hotel_id or name:
            hotels.append({"id": hotel_id, "name": name})
    box = (data.get("place") or {}).get("searchBox")
    return {"validJson": True, "place": box, "hotels": hotels}


def collect(destinations):
    session = requests.Session()
    print("=== homepage (establish session) ===")
    session_response = get_page(session, HOMEPAGE_URL)
    print("session status:", session_response.status_code)

    print("\n=== homepage (read frontend config) ===")
    homepage = get_page(session, HOMEPAGE_URL)
    body = homepage.text
    candidates = find_endpoints(body, homepage.url or HOMEPAGE_URL)
    if not candidates:
        raise RuntimeError("No API endpoint found in the homepage HTML.")

    print("candidate endpoints:")
    for candidate in candidates[:8]:
        print(f"  score {candidate['score']}: {candidate['url']}")

    endpoint = candidates[0]["url"]
    print("selected endpoint:", endpoint)
    api_key = find_api_key_near(body, endpoint)
    catalog_url = build_catalog_request_url(endpoint)
    print("catalog request:", catalog_url)

    extra_headers = {"Accept": "application/json", "Accept-Language": "en"}
    if api_key:
        extra_headers["Apikey"] = api_key
        print("attached Apikey from the same page config")

    print("\n=== discovered endpoint (same cookie jar) ===")
    api = get_page(session, catalog_url, extra_headers)
    print("API status:", api.status_code)
    OUTPUT_FILE.write_text(api.text, encoding="utf-8")
    print("saved:", OUTPUT_FILE, f"({len(api.text)} bytes)")

    parsed = parse_catalog(api.text)
    print("catalog json valid:", parsed["validJson"])
    print("place search box:", "present" if parsed["place"] else "absent")
    print("hotel records:", len(parsed["hotels"]))

    algolia_config = read_json_attribute(body, "algolia-config")
    queries = destinations or ["paris", "london", "tokyo"]
    if not algolia_config or not algolia_config.get("appId") or not algolia_config.get("apiKey"):
        raise RuntimeError("Algolia search config was not found in the homepage.")

    results = []
    indices = algolia_config.get("indices") or {}
    for destination in queries:
        results.append(
            search_destination(
                session,
                destination,
                algolia_config["appId"],
                algolia_config["apiKey"],
                indices.get("places"),
                indices.get("hotels"),
                endpoint,
                api_key,
            )
        )

    stored_reese = any(cookie.name == "reese84" for cookie in session.cookies)
    print("\n=== session check ===")
    print("[1] homepage session:", session_response.status_code == 200)
    print("[2] reese84 received from Set-Cookie:", stored_reese)
    print("[3] reese84 stored in cookie jar:", stored_reese)
    print("[4] api key obtained:", bool(api_key))
    print("[5] catalog request sent Apikey:", bool(api_key))
    print("[6] catalog response parsed:", parsed["validJson"])
    print("[7] catalog payload hotel rows:", len(parsed["hotels"]))

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "destinations": results,
    }


def main(destinations=None):
    if destinations is None:
        destinations = sys.argv[1:]
    return collect(destinations)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error)
        raise SystemExit(1) from error
