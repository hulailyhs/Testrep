#!/usr/bin/env python3
"""Generate refined-Bohemian renders for each space of the ground-floor plan.

Sends ground-floor-plan.jpg as a layout reference with one prompt per view to
the Gemini image API. Reads the key only from GEMINI_API_KEY (never pass it on
the command line). Every image is a paid request.

    python3 generate_renders.py --list                 # show spaces, no cost
    python3 generate_renders.py --dry-run              # print prompts, no cost
    python3 generate_renders.py majlis kitchen         # only these spaces
    python3 generate_renders.py                        # every view
"""
import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
PLAN = HERE / "ground-floor-plan.jpg"
OUT = HERE / "renders"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.1-flash-image"

STYLE = (
    "Refined, upscale Bohemian interior style for a modern Gulf family villa: "
    "calm and respectable, never cluttered. Warm earthy palette of sand, ivory, "
    "terracotta, olive and cognac with small indigo accents. Materials: honed "
    "travertine and warm limestone, lime plaster / tadelakt walls, natural oak "
    "and walnut joinery, rattan and cane panels, hand-knotted wool and jute "
    "rugs, linen and boucle upholstery, handmade zellige tiles, brushed brass "
    "details, arched openings and niches, woven pendant lights, generous indoor "
    "plants and olive trees. Photorealistic architectural visualisation, soft "
    "natural daylight, eye-level camera, 24mm lens, high detail, no people, "
    "no text, no watermarks."
)

LAYOUT = (
    "The attached image is the ground-floor architectural plan of the villa "
    "(plot about 19.5 m x 26.4 m). Respect the plan: keep the room's shape, "
    "proportions, door and window positions and its relation to neighbouring "
    "spaces. Space to render: "
)

# key -> (Arabic name, plan reference, [view prompts])
SPACES = {
    "facade": ("الواجهة الأمامية", "front elevation on the 30 m street", [
        "Exterior front facade of the two-storey villa seen from the 30 m street at golden hour. "
        "Limestone and lime-plaster facade, tall arched timber entrance door, rattan-screened "
        "windows, a round sculptural planter with an olive tree and date palms in the front yard, "
        "warm wall washers.",
        "Close view of the main entrance steps and arched wooden door with brass hardware, "
        "terracotta pots, layered planting and warm evening lighting.",
    ]),
    "pool": ("حوش المسبح والجلسة الخارجية", "swimming pool courtyard with outdoor sitting (centre-north)", [
        "Central courtyard with a rectangular swimming pool lined in green zellige, timber deck, "
        "date palms along the edge, a shaded outdoor sitting area with low built-in seating, "
        "linen cushions, kilim pillows, jute rug and woven lanterns, viewed from the family living room.",
        "Outdoor sitting area under a timber pergola with rattan shade, floor cushions, low brass "
        "tray tables and lanterns at dusk, pool reflecting warm light.",
        "Aerial three-quarter view of the courtyard showing pool, deck, palms and outdoor sitting.",
    ]),
    "parking": ("مواقف السيارات والممر الجانبي", "two-car parking and the side yard along the 6 m sikka", [
        "Two-car covered parking with travertine paving, slatted timber gate, vertical garden wall "
        "and warm downlights, minimal and elegant.",
        "Narrow side garden walkway along the boundary wall with stepping stones, gravel, date palms "
        "and low pathway lights.",
    ]),
    "entrance": ("المدخل الرئيسي", "main entrance hall GF-12", [
        "Main entrance foyer: arched niche with a carved console, round woven mirror, travertine "
        "floor with a hand-knotted runner, olive tree in a terracotta pot, brass pendant.",
        "Entrance hall looking toward the majlis double doors, with built-in shoe cabinet in cane "
        "and oak, soft indirect lighting.",
    ]),
    "majlis": ("المجلس", "majlis GF-13, about 5.1 m x 6.1 m", [
        "Formal Arabic majlis in refined Bohemian style: U-shaped low seating in ivory boucle with "
        "terracotta and indigo kilim cushions, large hand-knotted rug, carved walnut coffee tables, "
        "tadelakt walls with arched niches, brass lanterns, coffee (dallah) corner.",
        "Majlis view toward the windows: linen sheer curtains, rattan pendant lights, "
        "decorative ceramic plates and a large olive tree.",
    ]),
    "living": ("الصالة العائلية والطعام", "family living and dining GF-05 with double-height void", [
        "Double-height family living room: deep linen sofa, rattan lounge chairs, layered jute and "
        "wool rugs, oversized woven pendant hanging through the double height, tall arched windows "
        "to the pool courtyard, plants and a bookshelf wall in oak.",
        "Dining area: solid oak table for eight with cane-back chairs, cluster of rattan pendants, "
        "built-in buffet with zellige backsplash, view to the kitchen.",
        "View from the dining area back toward the staircase and family entrance, showing the "
        "double-height void and gallery above.",
    ]),
    "kitchen": ("المطبخ", "kitchen GF-04 with central island", [
        "Kitchen with large central island in travertine on oak base, olive-green lower cabinets "
        "with cane inserts, open oak shelves with ceramics, handmade zellige backsplash, brass "
        "fixtures, woven bar stools, integrated refrigerator.",
        "Kitchen detail: cooking wall with plaster range hood, terracotta tiles and herbs on the "
        "window sill.",
    ]),
    "multipurpose": ("الغرفة متعددة الاستخدامات", "multipurpose room GF-06, about 4.5 m x 4.2 m", [
        "Multipurpose room used as a library and family lounge: daybed with linen cushions, "
        "floor-to-ceiling oak shelving, reading chair, macramé wall piece, plants, writing desk.",
        "Same room set up for kids' play and study, with low storage, floor cushions and a soft rug.",
    ]),
    "guest_bedroom": ("غرفة نوم الضيوف", "guest bedroom GF-11, about 4.5 m x 4.0 m, with bath and closet", [
        "Guest bedroom: upholstered linen bed with a rattan arched headboard, layered bedding in "
        "sand and terracotta, woven pendant, bedside niches, jute rug, sheer curtains.",
        "Guest bedroom view toward the closet and bathroom doors, with a reading corner and plants.",
    ]),
    "stair": ("الدرج والمصعد", "staircase, lift and family entrance GF-07 / GF-08", [
        "Staircase with travertine treads and a plastered balustrade, oversized woven pendant in "
        "the stairwell, gallery wall of framed textiles, lift door clad in oak.",
    ]),
    "bathrooms": ("الحمامات ودورات المياه", "bath 02, washrooms 01/02 and toilets 01/02", [
        "Guest powder room: tadelakt walls, carved stone basin on an oak vanity, round brass mirror, "
        "zellige floor, woven pendant.",
        "Guest bathroom with walk-in shower in terracotta zellige, arched niche, brass fittings, "
        "linen towels and plants.",
    ]),
    "abaya": ("غرفة العبايات", "abaya room GF-15 by the side entrance", [
        "Small abaya and coat room: oak and cane wardrobes, upholstered bench, full-height arched "
        "mirror, brass hooks, soft lighting.",
    ]),
}


def views(selected):
    for key in selected:
        name, ref, prompts = SPACES[key]
        for i, prompt in enumerate(prompts, 1):
            yield key, name, i, f"{LAYOUT}{ref}. View: {prompt}\n\nStyle: {STYLE}"


def generate(model, key, prompt, plan_b64, aspect):
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": plan_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }
    req = urllib.request.Request(
        API.format(model=model),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline:
                return base64.b64decode(inline["data"]), inline.get("mimeType", "image/png")
    raise RuntimeError(f"no image returned: {json.dumps(data)[:500]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spaces", nargs="*", help=f"subset of: {', '.join(SPACES)}")
    ap.add_argument("--model", default=os.environ.get("NANOBANANA_MODEL", DEFAULT_MODEL))
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--list", action="store_true", help="list spaces and exit")
    ap.add_argument("--dry-run", action="store_true", help="print prompts without calling the API")
    args = ap.parse_args()

    if args.list:
        for key, (name, ref, prompts) in SPACES.items():
            print(f"{key:14} {len(prompts)} views  {name}  ({ref})")
        return

    unknown = [s for s in args.spaces if s not in SPACES]
    if unknown:
        sys.exit(f"unknown space(s): {', '.join(unknown)}; run --list")
    jobs = list(views(args.spaces or SPACES))

    if args.dry_run:
        for key, name, i, prompt in jobs:
            print(f"=== {key}_{i} ({name}) ===\n{prompt}\n")
        print(f"{len(jobs)} images would be requested from {args.model}.")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Set GEMINI_API_KEY in your environment first.")
    plan_b64 = base64.b64encode(PLAN.read_bytes()).decode()
    OUT.mkdir(exist_ok=True)
    print(f"Requesting {len(jobs)} paid images from {args.model}...")
    failed = 0
    for key, name, i, prompt in jobs:
        try:
            img, mime = generate(args.model, api_key, prompt, plan_b64, args.aspect)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            detail = exc.read().decode()[:300] if isinstance(exc, urllib.error.HTTPError) else exc
            print(f"FAILED {key}_{i}: {detail}", file=sys.stderr)
            failed += 1
            continue
        path = OUT / f"{key}_{i}.{'jpg' if 'jpeg' in mime else 'png'}"
        path.write_bytes(img)
        print(f"saved {path.relative_to(HERE)}  ({name})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
