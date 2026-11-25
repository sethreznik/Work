"""Identify landmarks (and, without GPS, places) in new Not Birds photos with Claude.

Used by sync.py for Not Birds photos that have no entry in
data/notbirds_notes.json yet. Claude looks at the photo (Flickr's 1024px
version) with whatever context there is (GPS place, date, the photo's other
Flickr album names) and returns a landmark name only when the photo's subject
is a specific, nameable building or structure it is confident about, and a
place only when the photo has no GPS and the place is clear.

Needs the `anthropic` package and ANTHROPIC_API_KEY. If either is missing,
sync.py carries on and retries next time.
"""
import json
import sys

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "landmark": {
            "type": "string",
            "description": "name of the specific building/structure that is the photo's main subject, or empty",
        },
        "place": {"type": "string", "description": "where the photo was taken, only if asked and clear; else empty"},
        "area": {"type": "string", "description": "borough, city or county for that place, or empty"},
        "region": {"type": "string", "description": "state or region for that place, or empty"},
        "country": {"type": "string", "description": "country for that place, or empty"},
    },
    "required": ["landmark", "place", "area", "region", "country"],
    "additionalProperties": False,
}

SYSTEM = """You help title photos on a personal photography site. Each photo is \
titled by its landmark when it shows a specific, nameable building or \
structure, otherwise by its place, otherwise by its date.

landmark: set it only when the photo's main subject is a specific, \
recognizable building, bridge, monument, station, museum or similar that you \
can name with confidence (e.g. "Empire State Building", "United Nations \
Secretariat", "Queensboro Bridge", "Union Station"). Use the common name. \
Leave it empty for ordinary streets, generic buildings, skylines where no \
single structure is the subject, people, nature, or anything you are not sure \
of. A wrong name is worse than no name.

place/area/region/country: fill these only when the request says the photo \
has no GPS AND the location is clear from the photo or its album names (e.g. \
an album called "Maine 2017" with a rocky coast -> place "Maine coast", \
region "Maine"). Use a park, neighborhood or landmark-level place name where \
you can, a city otherwise. Otherwise leave all four empty. Never guess."""


def _content(req):
    ctx = [
        f"Taken: {req.get('taken') or 'unknown'}",
        f"GPS place: {req['gps_place']}" if req.get("gps_place") else
        "This photo has NO GPS; fill place/area/region/country only if clear.",
        f"Its other Flickr albums: {', '.join(req['albums'])}" if req.get("albums") else "Not in any other album.",
    ]
    return [
        {"type": "image", "source": {"type": "url", "url": req["image"]}},
        {"type": "text", "text": "\n".join(ctx) + "\n\nTitle this photo."},
    ]


def identify(requests):
    """Return [(request, result_or_None, error_or_None)]; failures retry next sync."""
    try:
        import anthropic
    except ImportError:
        return [(r, None, "anthropic package not installed") for r in requests]

    client = anthropic.Anthropic()
    out = []
    for req in requests:
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
                system=SYSTEM,
                messages=[{"role": "user", "content": _content(req)}],
            )
        except anthropic.AuthenticationError:
            return out + [(r, None, "Anthropic API credentials missing or invalid (set ANTHROPIC_API_KEY)")
                          for r in requests[len(out):]]
        except anthropic.RateLimitError as e:
            out.append((req, None, f"rate limited: {e.message}"))
            continue
        except anthropic.APIStatusError as e:
            out.append((req, None, f"API error {e.status_code}: {e.message}"))
            continue
        except anthropic.APIConnectionError as e:
            out.append((req, None, f"connection error: {e}"))
            continue
        except Exception as e:
            if "authentication" in str(e).lower():
                return out + [(r, None, "no Anthropic API key (set the ANTHROPIC_API_KEY secret)")
                              for r in requests[len(out):]]
            out.append((req, None, f"{type(e).__name__}: {e}"))
            continue

        if response.stop_reason in ("refusal", "max_tokens"):
            out.append((req, None, f"no result (stop_reason={response.stop_reason})"))
            continue
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            out.append((req, json.loads(text), None))
        except json.JSONDecodeError:
            out.append((req, None, "response was not valid JSON"))
            continue
        print(f"  Claude reviewed Not Birds photo {req['id']}", file=sys.stderr)
    return out
