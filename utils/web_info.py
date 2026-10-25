"""
Small, key-free web lookups (roadmap 3.7):

  weather   Open-Meteo (geocoding + forecast)
  news      Google News RSS (top stories or a topic)
  answers   Wikipedia (search + page summary)
  pages     fetch a URL and pull out its readable text (summarised by the model elsewhere)

Every function raises WebError with a message that is safe to show the user.
"""

import re
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

import requests

from utils.logger import get_logger

logger = get_logger(__name__)

TIMEOUT = 8
USER_AGENT = "ProjectHina/3 (desktop assistant; https://github.com/Parthiv-P-maker/PROJECT_HINA)"
MAX_PAGE_BYTES = 2_000_000


class WebError(Exception):
    """str(exc) is safe to show to the user."""


OFFLINE = "I can't reach the internet right now 🌐"


def _get(url, params=None, **kwargs):
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT,
                                headers={"User-Agent": USER_AGENT}, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        logger.warning("GET %s failed: %s", url, exc)
        raise WebError(OFFLINE) from exc


# =========================
# WEATHER
# =========================

WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "violent rain showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def geocode(city):
    """(display name, latitude, longitude) for a city name."""
    name, _, country_hint = city.partition(",")  # "Kochi, Japan" picks the country explicitly
    data = _get("https://geocoding-api.open-meteo.com/v1/search",
                {"name": name.strip(), "count": 10, "language": "en", "format": "json"}).json()
    results = data.get("results") or []
    if not results:
        raise WebError(f"I couldn't find a place called {city} 🌐")
    # Same-name towns: an explicit country wins, then the user's region (settings "news_region"), then the biggest.
    hint = country_hint.strip().lower()
    _, home, _ = _region()
    place = (next((r for r in results if hint and hint in (r.get("country") or "").lower()), None)
             or next((r for r in results if not hint and r.get("country_code") == home), None)
             or results[0])
    name = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
    return name, place["latitude"], place["longitude"]


def weather(city, day=0):
    """A one-line forecast for today (day=0) or tomorrow (day=1)."""
    name, lat, lon = geocode(city)
    data = _get("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }).json()
    daily = data.get("daily") or {}
    try:
        high, low = round(daily["temperature_2m_max"][day]), round(daily["temperature_2m_min"][day])
        rain = daily.get("precipitation_probability_max", [None, None])[day]
        sky = WEATHER_CODES.get(daily["weather_code"][day], "mixed weather")
    except (KeyError, IndexError, TypeError) as exc:
        raise WebError("The weather service sent something I couldn't read 🌐") from exc
    rain_note = f", {rain}% chance of rain" if rain is not None else ""
    if day == 0 and data.get("current"):
        now = data["current"]
        sky_now = WEATHER_CODES.get(now.get("weather_code"), sky)
        return (f"{name}: {round(now['temperature_2m'])}°C and {sky_now} now "
                f"(feels like {round(now['apparent_temperature'])}°C). Today {low} to {high}°C{rain_note}.")
    return f"{name} tomorrow: {sky}, {low} to {high}°C{rain_note}."


def rain_chance(city, day=0):
    """(display name, chance of rain in percent or None)."""
    name, lat, lon = geocode(city)
    data = _get("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
        "daily": "precipitation_probability_max"}).json()
    try:
        return name, (data.get("daily") or {})["precipitation_probability_max"][day]
    except (KeyError, IndexError, TypeError):
        return name, None


# =========================
# NEWS
# =========================

NEWS_REGION = ("en-IN", "IN", "IN:en")  # hl, gl, ceid; changeable in settings ("news_region": "US")


def _region():
    try:
        from ui_qt import settings as settings_mod
        country = (settings_mod.load().get("news_region") or "IN").upper()
    except Exception:
        country = "IN"
    return f"en-{country}", country, f"{country}:en"


def headlines(topic=None, count=3):
    """[(title, source)] from Google News: top stories, or stories about `topic`."""
    hl, gl, ceid = _region()
    if topic:
        url = "https://news.google.com/rss/search"
        params = {"q": topic, "hl": hl, "gl": gl, "ceid": ceid}
    else:
        url, params = "https://news.google.com/rss", {"hl": hl, "gl": gl, "ceid": ceid}
    try:
        root = ET.fromstring(_get(url, params).content)
    except ET.ParseError as exc:
        raise WebError("The news feed sent something I couldn't read 🌐") from exc
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[:-len(" - " + source)]
        if title:
            out.append((title, source))
        if len(out) >= count:
            break
    return out


# =========================
# QUICK ANSWERS (Wikipedia)
# =========================

def wiki_summary(query, max_chars=420):
    """(page title, first few sentences) of the best Wikipedia match."""
    data = _get("https://en.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"}).json()
    hits = ((data.get("query") or {}).get("search")) or []
    if not hits:
        raise WebError(f"Wikipedia has nothing on {query} 🌐")
    title = hits[0]["title"]
    page = _get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))).json()
    extract = (page.get("extract") or "").strip()
    if not extract or page.get("type") == "disambiguation":
        raise WebError(f"\"{query}\" could mean several things. Can you be more specific? 🌐")
    return page.get("title") or title, _trim_sentences(extract, max_chars)


def _trim_sentences(text, max_chars):
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", cut)]
    return cut[:ends[-1]] if ends else cut.rstrip() + "..."


# =========================
# WEB PAGES
# =========================

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def find_url(text):
    match = URL_RE.search(text or "")
    return match.group(0).rstrip(").,;") if match else None


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "br", "tr", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skipping:
            self.parts.append(data)


def page_text(url):
    """(page title, readable text) of a web page."""
    if urlparse(url).scheme not in ("http", "https"):
        raise WebError("I can only read http(s) links 🌐")
    response = _get(url, stream=True)
    kind = response.headers.get("Content-Type", "")
    if "html" not in kind and "text" not in kind:
        raise WebError("That link isn't a web page I can read (it looks like a file) 🌐")
    body = response.raw.read(MAX_PAGE_BYTES, decode_content=True)
    html = body.decode(response.encoding or "utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).split("\n")]
    text = "\n".join(line for line in lines if len(line) > 30)  # drop menus and button labels
    if not text:
        raise WebError("I couldn't find any readable text on that page 🌐")
    return re.sub(r"\s+", " ", parser.title).strip(), text


def today():
    return date.today()
