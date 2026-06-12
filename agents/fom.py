"""Field-of-membership verification: given an address, confirm it's a real
place (geocode) and inside our membership districts, with an evidence chain.

Geocoding: Google Maps when GOOGLE_MAPS_API_KEY is set, falling back to
Nominatim/OpenStreetMap (free, no key). Either failing → UNVERIFIABLE,
never an exception.

  uv run python -m agents.fom "301 W 2nd St, Austin, TX"
"""

import sys
import time

import requests

import config
from sources.base import TIMEOUT

# Our charter: persons who live, work, worship, or attend school in these
# counties (a realistic community-charter FOM for a demo credit union).
# A real deployment drops its actual charter in data/fom_charter.json
# (gitignored): {"region": "...", "states": ["..."], "districts": {...}}.
FOM_DISTRICTS = {
    "Travis County": "TX-CU charter §5.01(a)",
    "Williamson County": "TX-CU charter §5.01(b)",
    "Hays County": "TX-CU charter §5.01(c)",
    "Bastrop County": "TX-CU charter §5.01(d)",
    "Caldwell County": "TX-CU charter §5.01(e)",
    "Burnet County": "TX-CU charter §5.01(f)",
}
FOM_STATES = ("Texas", "TX")
FOM_REGION = "Central Texas"

try:
    import json as _json
    _local = _json.loads((config.DATA_DIR / "fom_charter.json").read_text())
    FOM_DISTRICTS = _local["districts"]
    FOM_STATES = tuple(_local["states"])
    FOM_REGION = _local.get("region", FOM_REGION)
except Exception:
    pass  # no local charter — demo defaults above

NOMINATIM_UA = "canary-regulatory-agent-hackathon/0.1 (demo)"


def _geocode_google(address: str) -> dict | None:
    resp = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": config.GOOGLE_MAPS_API_KEY},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "OK" or not body.get("results"):
        return None
    r = body["results"][0]
    comps = {t: c["long_name"] for c in r["address_components"] for t in c["types"]}
    return {
        "provider": "google-maps",
        "display_name": r.get("formatted_address", address),
        "lat": r["geometry"]["location"]["lat"],
        "lon": r["geometry"]["location"]["lng"],
        "county": comps.get("administrative_area_level_2"),
        "state": comps.get("administrative_area_level_1"),
        "precision": r["geometry"].get("location_type", "UNKNOWN"),
        "partial_match": bool(r.get("partial_match")),
    }


def _geocode_nominatim(address: str) -> dict | None:
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "jsonv2", "addressdetails": 1,
                "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": NOMINATIM_UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body:
        return None
    r = body[0]
    addr = r.get("address", {})
    return {
        "provider": "nominatim-osm",
        "display_name": r.get("display_name", address),
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "county": addr.get("county"),
        "state": addr.get("state"),
        "precision": r.get("type", "unknown"),
        "partial_match": False,
    }


def verify_membership(address: str) -> dict:
    """Returns {status, address, geocode, county, evidence: [steps...]}."""
    evidence: list[dict] = []
    result = {"status": "UNVERIFIABLE", "address": address, "geocode": None,
              "county": None, "evidence": evidence}

    geo = None
    providers = ([("google-maps", _geocode_google)] if config.GOOGLE_MAPS_API_KEY else [])
    providers.append(("nominatim-osm", _geocode_nominatim))
    for provider_name, fn in providers:
        try:
            geo = fn(address)
            if geo:
                evidence.append({
                    "step": "geocode", "source": provider_name, "result": "resolved",
                    "detail": f"{geo['display_name']} @ ({geo['lat']:.5f}, {geo['lon']:.5f}), "
                              f"precision={geo['precision']}",
                })
                break
            evidence.append({"step": "geocode", "source": provider_name,
                             "result": "no-match", "detail": "no results for address"})
        except Exception as exc:
            evidence.append({"step": "geocode", "source": provider_name,
                             "result": "error", "detail": f"{type(exc).__name__}: {exc}"})

    if not geo:
        evidence.append({"step": "decision", "source": "fom-policy", "result": "UNVERIFIABLE",
                         "detail": "address did not resolve to a real place via any geocoder"})
        return result
    result["geocode"] = geo

    evidence.append({"step": "real-place-check", "source": geo["provider"], "result": "pass",
                     "detail": "address resolves to a physical location"
                               + (" (partial match — verify with member)" if geo["partial_match"] else "")})

    state, county = geo.get("state"), geo.get("county")
    result["county"] = county
    if state and state not in FOM_STATES:
        result["status"] = "NOT_ELIGIBLE"
        evidence.append({"step": "district-check", "source": "fom-policy", "result": "fail",
                         "detail": f"resolved state is {state}; charter covers {FOM_STATES[0]} counties only"})
    elif county and county in FOM_DISTRICTS:
        result["status"] = "ELIGIBLE"
        evidence.append({"step": "district-check", "source": "fom-policy", "result": "pass",
                         "detail": f"{county} is within field of membership ({FOM_DISTRICTS[county]})"})
    elif county:
        result["status"] = "NOT_ELIGIBLE"
        evidence.append({"step": "district-check", "source": "fom-policy", "result": "fail",
                         "detail": f"{county}, {state} is outside our membership districts "
                                   f"({', '.join(FOM_DISTRICTS)})"})
    else:
        evidence.append({"step": "district-check", "source": "fom-policy", "result": "indeterminate",
                         "detail": "geocoder returned no county; cannot map to a district"})

    evidence.append({"step": "decision", "source": "fom-policy", "result": result["status"],
                     "detail": f"membership eligibility for '{address}': {result['status']}"})

    # FOM checks are autonomous decisions — they still leave an audit trail.
    # Written off the hot path: the answer must never wait on the sink.
    def _audit_async():
        try:
            from harness import db
            conn = db.connect()
            db.audit(conn, "fom_verify", "fom-tool", result["status"], "autonomous",
                     f"address '{address}' → {result['status']}"
                     f" ({county or 'no county'}, geocoder={geo['provider'] if geo else 'none'})")
            conn.close()
        except Exception:
            pass
    import threading
    threading.Thread(target=_audit_async, daemon=True).start()

    return result


def format_evidence(result: dict) -> str:
    lines = [f"  {result['status']} — {result['address']}"]
    for e in result["evidence"]:
        lines.append(f"    [{e['step']} via {e['source']}] {e['result']}: {e['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    addresses = sys.argv[1:] or [
        "301 W 2nd Street, Austin, TX 78701",         # ELIGIBLE
        "1 World Trade Center, Los Angeles, CA",      # NOT_ELIGIBLE (out of state)
        "123 Imaginary Blvd, Nowhereville, ZZ 00000", # UNVERIFIABLE
    ]
    for addr in addresses:
        print(format_evidence(verify_membership(addr)))
        time.sleep(1.1)  # Nominatim usage policy: max 1 req/sec
