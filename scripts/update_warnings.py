#!/usr/bin/env python3
import json
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

UA = "IPNU-Disaster-Signage/1.1"

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

def iter_entries(feed_bytes):
    root = ET.fromstring(feed_bytes)
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
            yield {
                "title": title,
                "updated": updated,
                "href": href,
            }

def control_title(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for el in root.iter():
        if lname(el.tag) == "Control":
            for c in list(el):
                if lname(c.tag) == "Title":
                    return (c.text or "").strip()
    return ""

def is_vpws50_candidate(entry):
    title = entry["title"]
    href = entry["href"]

    # URL側にデータ種別コードが入っていれば最優先
    if "VPWS50" in href.upper():
        return True

    # フィード側の表記ゆれに対応して広く候補化
    if "気象警報・注意報" in title:
        return True
    if "警報・注意報" in title and "集約" in title:
        return True

    return False

def report_datetime(root):
    # Head/ReportDateTime があれば優先
    for wanted in ("ReportDateTime", "TargetDateTime", "DateTime"):
        for el in root.iter():
            if lname(el.tag) == wanted and (el.text or "").strip():
                return (el.text or "").strip()
    return ""

def find_city_warning_roots(root):
    roots = []
    for el in root.iter():
        if lname(el.tag) != "Warning":
            continue
        typ = el.attrib.get("type", "")
        if "市町村" in typ:
            roots.append(el)

    # 新仕様でtype文字列が変わっても最終的に全体走査可能
    return roots if roots else [root]

def parse_report(xml_bytes):
    root = ET.fromstring(xml_bytes)

    ctl_title = control_title(xml_bytes)
    if "気象警報・注意報" not in ctl_title or "集約" not in ctl_title:
        raise ValueError(f"Not VPWS50 aggregate report: {ctl_title}")

    result = {code: [] for code in ISHIKAWA}

    for search_root in find_city_warning_roots(root):
        for item in search_root.iter():
            if lname(item.tag) != "Item":
                continue

            area = None
            kinds = []

            for c in list(item):
                n = lname(c.tag)
                if n == "Area":
                    area = c
                elif n == "Kind":
                    kinds.append(c)

            if area is None:
                continue

            code = child_text(area, "Code")
            if code not in ISHIKAWA:
                continue

            for kind in kinds:
                status = child_text(kind, "Status")
                name = child_text(kind, "Name")

                # Nameが深い階層の場合も拾う
                if not name:
                    for x in kind.iter():
                        if lname(x.tag) == "Name":
                            txt = (x.text or "").strip()
                            if txt:
                                name = txt
                                break

                if not name:
                    continue

                # 解除済みは表示しない
                if "解除" in status:
                    continue
                if "発表警報・注意報はなし" in status:
                    continue

                # 汎用見出しは除外
                if name in ("気象警報・注意報", "警報・注意報"):
                    continue

                obj = {"name": name, "status": status}
                if obj not in result[code]:
                    result[code].append(obj)

    return {
        "control_title": ctl_title,
        "report_datetime": report_datetime(root),
        "municipalities": [
            {
                "code": code,
                "name": ISHIKAWA[code],
                "warnings": result[code],
            }
            for code in ISHIKAWA
        ],
    }

def main():
    entries = []
    feed_errors = []

    for feed in FEEDS:
        try:
            feed_bytes = get(feed)
            entries.extend(iter_entries(feed_bytes))
        except Exception as e:
            feed_errors.append(f"{feed}: {e}")

    if not entries:
        raise RuntimeError("No Atom entries read: " + "; ".join(feed_errors))

    # 新しい順
    entries.sort(key=lambda x: x["updated"], reverse=True)

    # まず警報関係だけを候補にする
    candidates = [e for e in entries if is_vpws50_candidate(e)]

    # 万一タイトル表記が想定外でも、直近entryを一定数確認する
    if not candidates:
        candidates = entries[:80]

    seen = set()
    errors = []

    for e in candidates[:120]:
        url = e["href"]
        if url in seen:
            continue
        seen.add(url)

        try:
            xml_bytes = get(url)

            # 実XMLのControl/TitleでVPWS50集約通報かを最終確認
            ctl = control_title(xml_bytes)
            if not ("気象警報・注意報" in ctl and "集約" in ctl):
                continue

            parsed = parse_report(xml_bytes)

            payload = {
                "ok": True,
                "source": "JMA VPWS50",
                "source_url": url,
                "feed_updated": e["updated"],
                "report_datetime": parsed["report_datetime"] or e["updated"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "municipalities": parsed["municipalities"],
            }

            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print("SUCCESS")
            print("Control/Title:", parsed["control_title"])
            print("Source:", url)
            print("Report datetime:", payload["report_datetime"])
            print("Wrote:", OUT)
            return

        except Exception as ex:
            errors.append(f"{url}: {ex}")

    # デバッグ情報をActionsログへ出す
    print("Recent Atom entries:")
    for e in entries[:30]:
        print("-", e["updated"], "|", e["title"], "|", e["href"])

    raise RuntimeError(
        "VPWS50 aggregate XML not found. "
        + (" | ".join(errors[-5:]) if errors else "")
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        payload = {
            "ok": False,
            "error": str(e),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "municipalities": [],
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise
