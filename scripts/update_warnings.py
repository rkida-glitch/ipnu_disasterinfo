#!/usr/bin/env python3
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FEEDS = [
    "https://www.data.jma.go.jp/developer/xml/feed/extra.xml",
    "https://www.data.jma.go.jp/developer/xml/feed/extra_l.xml",
]

OUT = Path("data/warnings.json")

ISHIKAWA = {
    "1720100":"金沢市","1720200":"七尾市","1720300":"小松市",
    "1720400":"輪島市","1720500":"珠洲市","1720600":"加賀市",
    "1720700":"羽咋市","1720900":"かほく市","1721000":"白山市",
    "1721100":"能美市","1721200":"野々市市","1732400":"川北町",
    "1736100":"津幡町","1736500":"内灘町","1738400":"志賀町",
    "1738600":"宝達志水町","1740700":"中能登町","1746100":"穴水町",
    "1746300":"能登町",
}

# 2026/5/28以降の新体系。
# VPWW55–61を対象とし、石川県を含む最新電文をデータ種類ごとに採用する。
PRODUCT_RE = re.compile(r"(VPWW(?:5[5-9]|60|61))_", re.I)

UA = "IPNU-Disaster-Signage/1.2"

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Cache-Control": "no-cache",
            "Accept": "application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

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

        if href:
            m = PRODUCT_RE.search(href)
            if m:
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
            code = child_text(c, "Code")
            name = child_text(c, "Name")
            return code, name
    return "", ""

def extract_kinds(item):
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

        # 解除・発表なしは表示しない
        if "解除" in status:
            continue
        if "発表警報・注意報はなし" in status:
            continue
        if "発表なし" == status:
            continue

        # 汎用見出しを除外
        if name in ("気象警報・注意報", "警報・注意報"):
            continue

        kinds.append({"name": name, "status": status})
    return kinds

def parse_ishikawa(xml_bytes):
    root = ET.fromstring(xml_bytes)
    found = {}
    encountered_codes = set()

    for item in root.iter():
        if lname(item.tag) != "Item":
            continue

        code, area_name = area_code_from_item(item)
        if code not in ISHIKAWA:
            continue

        encountered_codes.add(code)
        warnings = extract_kinds(item)

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

def main():
    entries = []
    feed_errors = []

    for feed in FEEDS:
        try:
            entries.extend(parse_feed(get(feed)))
        except Exception as e:
            feed_errors.append(f"{feed}: {e}")

    if not entries:
        raise RuntimeError(
            "No VPWW55-61 entries found in JMA Atom feed. "
            + "; ".join(feed_errors)
        )

    # 新しい順。URL重複を除く。
    entries.sort(key=lambda x: x["updated"], reverse=True)
    seen_urls = set()
    unique_entries = []
    for e in entries:
        if e["href"] in seen_urls:
            continue
        seen_urls.add(e["href"])
        unique_entries.append(e)

    # データ種類ごとに「石川県を含む最新電文」を1つずつ採用。
    selected = {}
    debug_checked = []

    for e in unique_entries[:350]:
        product = e["product"]

        # 既にこの種類の石川県電文を取得済みならスキップ
        if product in selected:
            continue

        try:
            xml_bytes = get(e["href"])
            parsed = parse_ishikawa(xml_bytes)

            debug_checked.append(
                (e["updated"], product, e["title"], parsed["control_title"],
                 len(parsed["encountered_codes"]), e["href"])
            )

            if parsed["contains_ishikawa"]:
                selected[product] = {
                    "entry": e,
                    "parsed": parsed,
                }

            # 主要な7種類を全部取れたら終了
            if len(selected) >= 7:
                break

        except Exception as ex:
            debug_checked.append(
                (e["updated"], product, e["title"], f"ERROR: {ex}", 0, e["href"])
            )

    if not selected:
        print("Checked recent VPWW55-61 entries:")
        for row in debug_checked[-80:]:
            print(" | ".join(map(str, row)))
        raise RuntimeError(
            "No recent VPWW55-61 document containing Ishikawa municipality codes was found."
        )

    # 各種類の最新石川県電文をマージ
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

    # 一番新しいreport datetimeを代表時刻にする
    report_times = [
        x["report_datetime"] for x in source_reports if x["report_datetime"]
    ]
    feed_times = [
        x["feed_updated"] for x in source_reports if x["feed_updated"]
    ]
    representative_time = (
        max(report_times) if report_times else
        max(feed_times) if feed_times else
        datetime.now(timezone.utc).isoformat()
    )

    payload = {
        "ok": True,
        "source": "JMA VPWW55-61",
        "report_datetime": representative_time,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_reports": source_reports,
        "municipalities": [
            {
                "code": code,
                "name": ISHIKAWA[code],
                "warnings": merged[code],
            }
            for code in ISHIKAWA
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("SUCCESS: Ishikawa warning data generated")
    print("Selected source reports:")
    for s in source_reports:
        print(
            f"- {s['product']} | {s['report_datetime']} | "
            f"{s['control_title']} | {s['source_url']}"
        )

    active = [
        (ISHIKAWA[c], [w["name"] for w in merged[c]])
        for c in ISHIKAWA if merged[c]
    ]
    print("Active warnings/advisories:")
    if active:
        for name, warnings in active:
            print("-", name, ":", ", ".join(warnings))
    else:
        print("- none")

    print("Wrote:", OUT)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps({
                "ok": False,
                "error": str(e),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "municipalities": [],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
