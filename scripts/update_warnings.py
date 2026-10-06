#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ----------------------------------------------------------------------
# Recommended source order for the public GitHub Pages signage
#   1) JMA R8 prefecture JSON used by the current JMA warning web frontend
#   2) Public JMA PULL Atom feed, Ishikawa VPWW55-61, when still present
#   3) If both fail, preserve the previous known-good warnings.json and fail Action
# ----------------------------------------------------------------------
R8_JSON_URL = "https://www.jma.go.jp/bosai/warning/data/r8/170000.json"
FEEDS = [
    "https://www.data.jma.go.jp/developer/xml/feed/extra.xml",
    "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml",
]
PRODUCT_RE = re.compile(r"(VPWW(?:5[5-9]|60|61))_", re.I)

OUT = Path("data/warnings.json")
UA = "IPNU-Disaster-Signage/3.0"

ISHIKAWA = {
    "1720100": "金沢市", "1720200": "七尾市", "1720300": "小松市",
    "1720400": "輪島市", "1720500": "珠洲市", "1720600": "加賀市",
    "1720700": "羽咋市", "1720900": "かほく市", "1721000": "白山市",
    "1721100": "能美市", "1721200": "野々市市", "1732400": "川北町",
    "1736100": "津幡町", "1736500": "内灘町", "1738400": "志賀町",
    "1738600": "宝達志水町", "1740700": "中能登町", "1746100": "穴水町",
    "1746300": "能登町",
}

WARNING_NAMES = {
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報",
}

INACTIVE_STATUSES = {"解除", "発表警報・注意報はなし", "発表なし"}


def get(url, attempts=3, timeout=30):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Accept": "application/json,application/xml,text/xml,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last_error = e
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise last_error


def parse_r8_json(data_bytes):
    docs = json.loads(data_bytes)
    if not isinstance(docs, list) or not docs:
        raise RuntimeError("R8 warning JSON root is not a non-empty list.")

    merged = {code: [] for code in ISHIKAWA}
    encountered_codes = set()
    report_times = []
    source_reports = []
    unknown_codes = set()

    for doc in docs:
        if not isinstance(doc, dict):
            raise RuntimeError("R8 warning JSON contains a non-object item.")

        product = str(doc.get("dataTypeCode", ""))
        warning = doc.get("warning")
        if not product or not isinstance(warning, dict):
            raise RuntimeError("R8 warning JSON item has an unexpected structure.")

        items = warning.get("class20Items")
        if not isinstance(items, list):
            raise RuntimeError(f"{product}: class20Items is missing or invalid.")

        dt = doc.get("reportDatetime")
        if isinstance(dt, str) and dt:
            report_times.append(dt)

        source_reports.append({
            "product": product,
            "report_datetime": dt or "",
            "publishing_office": doc.get("publishingOffice", ""),
            "source_url": R8_JSON_URL,
        })

        for item in items:
            if not isinstance(item, dict):
                continue

            area_code = str(item.get("areaCode", ""))
            if area_code not in ISHIKAWA:
                continue

            encountered_codes.add(area_code)
            kinds = item.get("kinds", [])
            if not isinstance(kinds, list):
                raise RuntimeError(f"{product}/{area_code}: kinds is not a list.")

            for kind in kinds:
                if not isinstance(kind, dict):
                    continue

                status = str(kind.get("status", "")).strip()
                if status in INACTIVE_STATUSES or "解除" in status:
                    continue

                code = str(kind.get("code", "")).strip()
                if not code:
                    raise RuntimeError(
                        f"{product}/{area_code}: active warning has no code "
                        f"(status={status!r})."
                    )

                name = WARNING_NAMES.get(code)
                if not name:
                    unknown_codes.add(code)
                    name = f"警報・注意報（コード{code}）"

                w = {"name": name, "status": status}
                if w not in merged[area_code]:
                    merged[area_code].append(w)

    if encountered_codes != set(ISHIKAWA):
        missing = sorted(set(ISHIKAWA) - encountered_codes)
        raise RuntimeError(
            "R8 warning JSON did not contain all Ishikawa municipalities. "
            f"Missing: {', '.join(missing)}"
        )

    if unknown_codes:
        print("::warning::Unknown active JMA warning code(s): " + ", ".join(sorted(unknown_codes)))

    return {
        "source": "JMA R8 warning JSON",
        "report_datetime": max(report_times) if report_times else "",
        "source_reports": source_reports,
        "warnings": merged,
    }


def fetch_from_r8_json():
    return parse_r8_json(get(R8_JSON_URL))


# ----------------------------------------------------------------------
# Fallback: public JMA PULL Atom feed, Ishikawa VPWW55-61 only
# ----------------------------------------------------------------------
def lname(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(node, name):
    for c in list(node):
        if lname(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_feed(feed_bytes):
    root = ET.fromstring(feed_bytes)
    items = []
    for e in root.iter():
        if lname(e.tag) != "entry":
            continue

        title = child_text(e, "title")
        updated = child_text(e, "updated")
        href = ""
        for c in list(e):
            if lname(c.tag) == "link" and c.attrib.get("href"):
                href = c.attrib["href"]
                break

        if not href:
            continue
        m = PRODUCT_RE.search(href)
        if not m:
            continue
        if not re.search(r"_170000\.xml(?:$|[?#])", href, re.I):
            continue

        items.append({
            "title": title,
            "updated": updated,
            "href": href,
            "product": m.group(1).upper(),
        })
    return items


def report_datetime(root):
    for wanted in ("ReportDateTime", "TargetDateTime", "DateTime"):
        for el in root.iter():
            if lname(el.tag) == wanted and (el.text or "").strip():
                return (el.text or "").strip()
    return ""


def control_title(root):
    for el in root.iter():
        if lname(el.tag) == "Control":
            for c in list(el):
                if lname(c.tag) == "Title":
                    return (c.text or "").strip()
    return ""


def area_code_from_item(item):
    for c in list(item):
        if lname(c.tag) == "Area":
            return child_text(c, "Code"), child_text(c, "Name")
    return "", ""


def extract_kinds_xml(item):
    kinds = []
    for c in list(item):
        if lname(c.tag) != "Kind":
            continue

        status = child_text(c, "Status")
        name = child_text(c, "Name")
        if not name:
            for x in c.iter():
                if lname(x.tag) == "Name" and (x.text or "").strip():
                    name = (x.text or "").strip()
                    break

        if not name:
            continue
        if status in INACTIVE_STATUSES or "解除" in status:
            continue
        if name in ("気象警報・注意報", "警報・注意報"):
            continue

        kinds.append({"name": name, "status": status})
    return kinds


def parse_ishikawa_vpww(xml_bytes):
    root = ET.fromstring(xml_bytes)
    found = {}
    encountered_codes = set()

    for item in root.iter():
        if lname(item.tag) != "Item":
            continue

        code, _ = area_code_from_item(item)
        if code not in ISHIKAWA:
            continue

        encountered_codes.add(code)
        warnings = extract_kinds_xml(item)
        if warnings:
            found.setdefault(code, [])
            for w in warnings:
                if w not in found[code]:
                    found[code].append(w)

    return {
        "contains_ishikawa": bool(encountered_codes),
        "encountered_codes": encountered_codes,
        "warnings": found,
        "report_datetime": report_datetime(root),
        "control_title": control_title(root),
    }


def fetch_from_vpww_feed():
    entries = []
    feed_errors = []

    for feed in FEEDS:
        try:
            entries.extend(parse_feed(get(feed)))
        except Exception as e:
            feed_errors.append(f"{feed}: {e}")

    if not entries:
        raise RuntimeError(
            "No Ishikawa (170000) VPWW55-61 entries found in JMA Atom feeds. "
            + "; ".join(feed_errors)
        )

    entries.sort(key=lambda x: x["updated"], reverse=True)
    seen = set()
    unique_entries = []
    for e in entries:
        if e["href"] in seen:
            continue
        seen.add(e["href"])
        unique_entries.append(e)

    selected = {}
    attempts_per_product = {}

    for e in unique_entries:
        product = e["product"]
        if product in selected:
            continue

        attempts_per_product[product] = attempts_per_product.get(product, 0) + 1
        if attempts_per_product[product] > 10:
            continue

        try:
            parsed = parse_ishikawa_vpww(get(e["href"]))
            if parsed["contains_ishikawa"]:
                selected[product] = {"entry": e, "parsed": parsed}
        except Exception as ex:
            print(f"::warning::{product} fallback candidate failed: {ex}")

    if not selected:
        raise RuntimeError("No usable Ishikawa VPWW55-61 documents were found in Atom feeds.")

    merged = {code: [] for code in ISHIKAWA}
    source_reports = []

    for product, obj in sorted(selected.items()):
        p = obj["parsed"]
        e = obj["entry"]
        source_reports.append({
            "product": product,
            "feed_updated": e["updated"],
            "report_datetime": p["report_datetime"],
            "control_title": p["control_title"],
            "source_url": e["href"],
        })
        for code, warnings in p["warnings"].items():
            for w in warnings:
                if w not in merged[code]:
                    merged[code].append(w)

    times = [x["report_datetime"] for x in source_reports if x["report_datetime"]]
    if not times:
        times = [x["feed_updated"] for x in source_reports if x.get("feed_updated")]

    return {
        "source": "JMA VPWW55-61 Atom feed (fallback)",
        "report_datetime": max(times) if times else "",
        "source_reports": source_reports,
        "warnings": merged,
    }


def build_payload(source_data):
    return {
        "ok": True,
        "source": source_data["source"],
        "report_datetime": source_data["report_datetime"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_reports": source_data["source_reports"],
        "municipalities": [
            {
                "code": code,
                "name": ISHIKAWA[code],
                "warnings": source_data["warnings"].get(code, []),
            }
            for code in ISHIKAWA
        ],
    }


def atomic_write_json(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)


def print_summary(payload):
    print("SUCCESS: Ishikawa warning data generated")
    print("Source:", payload["source"])
    print("Report datetime:", payload["report_datetime"])
    print("Generated at:", payload["generated_at"])

    active = [
        (m["name"], [w["name"] for w in m["warnings"]])
        for m in payload["municipalities"]
        if m["warnings"]
    ]
    print("Active warnings/advisories:")
    if active:
        for name, warnings in active:
            print("-", name, ":", ", ".join(warnings))
    else:
        print("- none")
    print("Wrote:", OUT)


def main():
    primary_error = None

    try:
        source_data = fetch_from_r8_json()
    except Exception as e:
        primary_error = e
        print(f"::warning::JMA R8 warning JSON primary source failed: {e}")
        print("Falling back to Ishikawa VPWW55-61 Atom feed...")
        source_data = fetch_from_vpww_feed()

    payload = build_payload(source_data)
    atomic_write_json(payload)
    print_summary(payload)

    if primary_error is not None:
        print(
            "::warning::This run succeeded via VPWW55-61 fallback. "
            "Review the JMA R8 JSON endpoint if fallback use continues."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Never replace the last known-good data with an error payload.
        print(f"ERROR: {e}")
        if OUT.exists():
            print(
                "Existing data/warnings.json was preserved "
                "(last known-good data remains available)."
            )
        raise
