"""Write field-guide entries for newly photographed species with Claude.

Used by sync.py when a Flickr title resolves to a species that isn't in
data/species.json. Each entry matches the hand-written ones: canonical common
name, scientific name, family, and a one- or two-sentence note.

Needs the `anthropic` package and credentials (ANTHROPIC_API_KEY in GitHub
Actions). If either is missing, sync.py carries on without new entries.
"""
import json
import sys

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "is_species": {
            "type": "boolean",
            "description": "true only if the title clearly names one bird species",
        },
        "reason": {
            "type": "string",
            "description": "if is_species is false: a short reason, e.g. 'too generic: several sparrow species'",
        },
        "name": {"type": "string", "description": "standard English common name (Clements/eBird)"},
        "scientific": {"type": "string", "description": "current scientific name (Clements/eBird)"},
        "family": {"type": "string", "description": "'Common family name (Latinidae)', matching the site's existing families"},
        "about": {"type": "string", "description": "one or two sentences, at most 35 words"},
    },
    "required": ["is_species", "reason", "name", "scientific", "family", "about"],
    "additionalProperties": False,
}

SYSTEM = """You write species entries for a personal bird photography site. \
Each entry is a short field-guide note shown beside the photographer's photo.

Given the title the photographer gave a photo on Flickr, plus where it was taken:
- Decide which species it is. Use the location to settle ambiguous names (a \
"Kestrel" in New York is an American Kestrel). If the title is too generic to \
name one species (e.g. "Sparrow", "Duck", "Gull"), misspelled beyond \
recognition, or not a bird, set is_species to false, explain in reason, and \
leave the other fields as empty strings.
- name: the standard English common name, capitalised as in Clements/eBird \
(e.g. "Red-winged Blackbird", "Black-crowned Night-Heron").
- scientific and family: current Clements/eBird taxonomy. Write family as \
"Common family name (Latinidae)" and reuse the site's existing family wording \
when the family is already on the site.
- about: one or two plain, accurate sentences (at most 35 words) on what makes \
the bird distinctive or interesting: a field mark, a behaviour, a notable fact. \
Match the tone of the examples. No first person, no exclamation marks, no \
mention of the photo or the photographer. If you are not sure a fact is right, \
leave it out."""


def _prompt(req, examples, families):
    ex = "\n".join(json.dumps(e, ensure_ascii=False) for e in examples)
    return (
        f"Existing entries on the site, for style:\n{ex}\n\n"
        f"Families already on the site:\n{', '.join(families)}\n\n"
        f"Flickr title: {req['title']!r}\n"
        f"Photographed at: {'; '.join(req['places']) or 'unknown'}\n"
        f"Photographer's caption: {req.get('caption') or 'none'}\n\n"
        "Write the entry."
    )


def write_entries(requests, examples, families):
    """Return a list of (request, result_or_None, error_or_None).

    result is the parsed JSON dict from SCHEMA. Network/API failures are
    returned as errors so the caller can retry on the next sync.
    """
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
                fallbacks="default",  # if a request is ever declined, retry on a fallback model
                output_config={
                    "effort": "high",  # accuracy of names and facts matters more than speed here
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
                system=SYSTEM,
                messages=[{"role": "user", "content": _prompt(req, examples, families)}],
            )
        except anthropic.AuthenticationError:
            # No point trying the rest with bad or missing credentials.
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
            if "authentication" in str(e).lower():  # no credentials configured at all
                return out + [(r, None, "no Anthropic API key (set the ANTHROPIC_API_KEY secret)")
                              for r in requests[len(out):]]
            out.append((req, None, f"{type(e).__name__}: {e}"))
            continue

        if response.stop_reason in ("refusal", "max_tokens"):
            out.append((req, None, f"no entry written (stop_reason={response.stop_reason})"))
            continue
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            out.append((req, json.loads(text), None))
        except json.JSONDecodeError:
            out.append((req, None, "response was not valid JSON"))
        print(f"  Claude wrote entry for {req['title']!r}", file=sys.stderr)
    return out
