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

UA = "IPNU-Disaster-Signage/1.0 (+GitHub Pages; JMA public data)"

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read()

def lname(tag):
    return tag.rsplit("}",1)[-1]

def child_text(node, name):
    for c in list(node):
        if lname(c.tag)==name:
            return (c.text or "").strip()
    return ""

def find_desc(node, name):
    for c in node.iter():
        if lname(c.tag)==name:
            return c
    return None

def extract_entries(feed_bytes):
    root=ET.fromstring(feed_bytes)
    entries=[]
    for e in root.iter():
        if lname(e.tag)!="entry":
            continue
        title=child_text(e,"title")
        updated=child_text(e,"updated")
        href=""
        for c in list(e):
            if lname(c.tag)=="link" and c.attrib.get("href"):
                href=c.attrib["href"]
                break
        if title=="気象警報・注意報（Ｒ０６）（集約通報）" and href:
            entries.append((updated,href))
    return entries

def extract_report(xml_bytes):
    root=ET.fromstring(xml_bytes)

    # report datetime
    report_dt=""
    for tagname in ("DateTime","ReportDateTime","TargetDateTime"):
        el=find_desc(root,tagname)
        if el is not None and el.text:
            report_dt=el.text.strip()
            break

    # Narrow to Warning type=気象警報・注意報（市町村等） if present
    warning_nodes=[]
    for el in root.iter():
        if lname(el.tag)=="Warning":
            typ=el.attrib.get("type","")
            if "市町村" in typ:
                warning_nodes.append(el)
    search_roots=warning_nodes if warning_nodes else [root]

    result={code:[] for code in ISHIKAWA}

    for sr in search_roots:
        for item in sr.iter():
            if lname(item.tag)!="Item":
                continue

            area=None
            kinds=[]
            for c in list(item):
                n=lname(c.tag)
                if n=="Area":
                    area=c
                elif n=="Kind":
                    kinds.append(c)

            if area is None:
                continue
            code=child_text(area,"Code")
            if code not in ISHIKAWA:
                continue

            for kind in kinds:
                status=child_text(kind,"Status")
                name=child_text(kind,"Name")

                # Aggregate message uses these statuses for no active warning.
                if "発表警報・注意報はなし" in status:
                    continue
                if status in ("解除","解除予定"):
                    continue

                # Some variants can place warning name deeper.
                if not name:
                    for x in kind.iter():
                        if lname(x.tag)=="Name" and (x.text or "").strip():
                            name=(x.text or "").strip()
                            break

                if not name:
                    continue

                # Ignore generic headings
                if name in ("気象警報・注意報","警報・注意報"):
                    continue

                obj={"name":name,"status":status}
                if obj not in result[code]:
                    result[code].append(obj)

    return report_dt, result

def main():
    entries=[]
    errors=[]
    for feed in FEEDS:
        try:
            entries.extend(extract_entries(get(feed)))
        except Exception as e:
            errors.append(f"{feed}: {e}")

    # newest first, avoid duplicates
    seen=set()
    entries=sorted(entries, reverse=True)
    entries=[x for x in entries if not (x[1] in seen or seen.add(x[1]))]

    if not entries:
        raise RuntimeError("VPWS50 entry not found: "+"; ".join(errors))

    last_err=None
    for updated,url in entries[:8]:
        try:
            report_dt, result=extract_report(get(url))
            # VPWS50 is nationwide; successful parse should encounter Ishikawa codes.
            # Even if all are 'none', result retains all 19 codes.
            payload={
                "ok":True,
                "source":"JMA VPWS50",
                "source_url":url,
                "feed_updated":updated,
                "report_datetime":report_dt or updated,
                "generated_at":datetime.now(timezone.utc).isoformat(),
                "municipalities":[
                    {"code":c,"name":ISHIKAWA[c],"warnings":result[c]}
                    for c in ISHIKAWA
                ],
            }
            OUT.parent.mkdir(parents=True,exist_ok=True)
            OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
            print("wrote",OUT,"from",url)
            return
        except Exception as e:
            last_err=e

    raise RuntimeError(f"Could not parse recent VPWS50: {last_err}")

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        payload={
            "ok":False,
            "error":str(e),
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "municipalities":[],
        }
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        raise
