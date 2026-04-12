#!/usr/bin/env python3
"""Simple web-page watch app for MLIT related URLs.

Usage examples:
  python monitor_app.py init-db
  python monitor_app.py seed-defaults
  python monitor_app.py list-monitors
  python monitor_app.py run-once --limit 5
  python monitor_app.py run-daemon --poll-sec 300
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Optional

DB_PATH = "watcher.db"
USER_AGENT = "HiroasaWatcher/1.0 (+https://example.local)"
TIMEOUT_SEC = 30


@dataclass(frozen=True)
class MonitorSeed:
    display_name: str
    url: str
    watch_type: str
    document_type: str
    category: str
    bureau_code: str
    interval_min: int
    note: str


SEEDS: list[MonitorSeed] = [
    MonitorSeed("技術調査関係報道発表資料（最新）", "https://www.mlit.go.jp/report/press/gijutsu_news.html", "HTML_HASH", "参考資料", "インフラDX", "PRESS", 30, "技術調査系の最新報道発表を一次検知。RSS補完推奨。"),
    MonitorSeed("技術調査：新着情報一覧", "https://www.mlit.go.jp/tec/news.html", "HTML_HASH", "参考資料", "インフラDX", "TEC", 30, "技術調査分野の新着一覧。RSS併用推奨。"),
    MonitorSeed("建設施工・建設機械：新着情報一覧", "https://www.mlit.go.jp/tec/constplan/news.html", "HTML_HASH", "参考資料", "ICT施工", "CONSTPLAN", 30, "施工系の新着集約。RSS併用推奨。"),
    MonitorSeed("BIM/CIM関連（技術調査）", "https://www.mlit.go.jp/tec/tec_tk_000037.html", "HTML_HASH", "参考資料", "BIM/CIM", "TEC", 60, "BIM/CIM最重要ハブ。"),
    MonitorSeed("BIM/CIM関連基準要領等（令和7年3月）", "https://www.mlit.go.jp/tec/tec_fr_000158.html", "HTML_HASH", "参考資料", "BIM/CIM", "TEC", 60, "年度版基準要領等のハブ。"),
    MonitorSeed("BIM/CIMポータル：基準・要領等（最新版）", "https://www.nilim.go.jp/lab/qbg/bimcim/standard.html", "HTML_HASH", "参考資料", "BIM/CIM", "NILIM", 60, "公式ポータル。"),
    MonitorSeed("BIM/CIMポータル：活用事例（検索/一覧）", "https://www.nilim.go.jp/lab/qbg/bimcim/usecase/index.html", "HTML_HASH", "参考資料", "BIM/CIM", "NILIM", 120, "事例更新監視。"),
    MonitorSeed("土木工事数量算出要領（令和7年度）", "https://www.nilim.go.jp/lab/pbg/theme/theme2/sr/yoryo0704.htm", "HTTP_META_THEN_HASH", "要領", "BIM/CIM", "NILIM", 360, "年度更新あり。"),
    MonitorSeed("公共測量：マニュアル・要領等のダウンロード（GSI）", "https://www.gsi.go.jp/gijyutukanri/gijyutukanri41021.html", "HTML_HASH", "マニュアル", "測量・3次元", "GSI", 120, "改正情報の集約。"),
    MonitorSeed("3次元数値地形図データ作成マニュアル（説明ページ）", "https://www.gsi.go.jp/gijyutukanri/gijyutukanri41029.html", "HTML_HASH", "マニュアル", "測量・3次元", "GSI", 120, "説明ページ更新監視。"),
    MonitorSeed("3次元数値地形図データ作成マニュアル（PDF）", "https://www.gsi.go.jp/common/000259826.pdf", "HTTP_META_THEN_HASH", "マニュアル", "測量・3次元", "GSI", 720, "PDF直リンク。ETag/Last-Modified優先。"),
    MonitorSeed("電子納品サイト（トップ）", "https://www.cals-ed.go.jp/", "HTML_HASH", "参考資料", "電子納品", "CALED", 120, "改定/停止告知監視。"),
    MonitorSeed("電子納品：要領・基準一覧（cri_point）", "https://www.cals-ed.go.jp/cri_point/", "HTML_HASH", "基準", "電子納品", "CALED", 120, "最新版リンク集。"),
    MonitorSeed("電子納品：改定のお知らせ（2024/03/29）", "https://www.cals-ed.go.jp/youryou-rev-20240329/", "HTML_HASH", "事務連絡", "電子納品", "CALED", 720, "改定告知ページ。"),
    MonitorSeed("電子納品：DTD・XML記入例", "https://www.cals-ed.go.jp/cri_dtdxml/", "HTML_HASH", "参考資料", "電子納品", "CALED", 120, "DTD/ZIP更新監視。"),
    MonitorSeed("i-Construction（新着一覧が長いトップ）", "https://www.mlit.go.jp/tec/i-construction/index.html", "HTML_HASH", "参考資料", "i-Construction", "TEC", 60, "時系列更新多め。"),
    MonitorSeed("i-Construction・インフラDX推進コンソーシアム（概要）", "https://www.mlit.go.jp/tec/i-construction/i-con_consortium/index.html", "HTML_HASH", "参考資料", "i-Construction", "TEC", 360, "更新頻度低め。"),
    MonitorSeed("i-Construction 2.0（策定：報道発表）", "https://www.mlit.go.jp/report/press/kanbo08_hh_001085.html", "HTML_HASH", "報告書", "i-Construction", "PRESS", 120, "本文PDFへの導線。"),
    MonitorSeed("i-Construction 2.0（本文PDF）", "https://www.mlit.go.jp/tec/constplan/content/001738240.pdf", "HTTP_META_THEN_HASH", "報告書", "i-Construction", "CONSTPLAN", 720, "方針本文PDF。"),
    MonitorSeed("ICTの全面的な活用（入口）", "https://www.mlit.go.jp/tec/constplan/sosei_constplan_tk_000031.html", "HTML_HASH", "参考資料", "ICT施工", "CONSTPLAN", 60, "メニュー集約ページ。"),
    MonitorSeed("ICTの全面的な活用：要領関係等（一覧）", "https://www.mlit.go.jp/tec/constplan/sosei_constplan_tk_000051.html", "HTML_HASH", "要領", "ICT施工", "CONSTPLAN", 60, "実施/積算要領の中核。"),
    MonitorSeed("国土交通省インフラ分野のDX（総合ハブ）", "https://www.mlit.go.jp/tec/tec_tk_000073.html", "HTML_HASH", "参考資料", "インフラDX", "TEC", 60, "DX関連総合ハブ。"),
    MonitorSeed("オープンデータ取組方針（本文PDF）", "https://www.mlit.go.jp/tec/content/001884707.pdf", "HTTP_META_THEN_HASH", "方針", "オープンデータ", "TEC", 720, "方針PDF。"),
    MonitorSeed("国土交通データプラットフォーム（技術調査ハブ）", "https://www.mlit.go.jp/tec/tec_tk_000066.html", "HTML_HASH", "参考資料", "データプラットフォーム", "TEC", 120, "DPFリンク集。"),
    MonitorSeed("国土交通DPF：データ連携標準仕様（案）Ver1.1（PDF）", "https://www.mlit.go.jp/tec/content/001901915.pdf", "HTTP_META_THEN_HASH", "基準", "データプラットフォーム", "TEC", 720, "標準仕様PDF。"),
    MonitorSeed("国土交通DPF：ドメイン変更（2026/01/20）報道発表", "https://www.mlit.go.jp/report/press/kanbo08_hh_001287.html", "HTML_HASH", "事務連絡", "データプラットフォーム", "PRESS", 360, "URL変更告知。"),
    MonitorSeed("xROAD（道路データプラットフォーム）トップ", "https://www.xroad.mlit.go.jp/", "HTML_HASH", "参考資料", "道路DX", "ROAD", 120, "導線集約ページ。"),
    MonitorSeed("xROAD：データベース一覧", "https://www.xroad.mlit.go.jp/database/", "HTML_HASH", "参考資料", "道路DX", "ROAD", 120, "DB追加/差替監視。"),
    MonitorSeed("xROAD：道路データビューア", "https://view.xroad.mlit.go.jp/", "HTTP_META_ONLY", "ツール", "道路DX", "ROAD", 720, "動的ページ想定、疎監視。"),
    MonitorSeed("PLATEAU（トップ）", "https://www.mlit.go.jp/plateau/", "HTML_HASH", "参考資料", "オープンデータ", "URBAN", 120, "PLATEAU入口。"),
    MonitorSeed("PLATEAU：News", "https://www.mlit.go.jp/plateau/news/", "HTML_HASH", "参考資料", "オープンデータ", "URBAN", 60, "ニュース追加監視。"),
    MonitorSeed("PLATEAU：Libraries（Recent Updatesあり）", "https://www.mlit.go.jp/plateau/libraries/", "HTML_HASH", "参考資料", "オープンデータ", "URBAN", 120, "技術資料の更新監視。"),
    MonitorSeed("PLATEAU：Open Data（Last update表示）", "https://www.mlit.go.jp/plateau/open-data/", "HTML_HASH", "参考資料", "オープンデータ", "URBAN", 120, "Last update表示あり。"),
    MonitorSeed("港湾：港湾におけるi-Construction（要領・委員会）", "https://www.mlit.go.jp/kowan/kowan_fr5_000061.html", "HTML_HASH", "実施方針", "港湾DX", "PORT", 120, "港湾ICT/BIM/CIMハブ。"),
    MonitorSeed("サイバーポート（港湾インフラ分野）ポータル", "https://www.cyber-port.mlit.go.jp/infra/", "HTML_HASH", "ツール", "港湾DX", "PORT", 360, "ポータル入口監視。"),
    MonitorSeed("港湾：サイバーポート（説明ページ）", "https://www.mlit.go.jp/kowan/kowan_00002.html", "HTML_HASH", "参考資料", "港湾DX", "PORT", 720, "更新低頻度。"),
    MonitorSeed("関東：インフラDXポータル（入口）", "https://www.ktr.mlit.go.jp/portal-dx/index.html", "HTML_HASH", "参考資料", "インフラDX", "KTR", 120, "局内標準リンク入口。"),
    MonitorSeed("関東：様式・基準（BIM/CIM・ICT・積算リンク集）", "https://www.ktr.mlit.go.jp/portal-dx/youshiki/index.html", "HTML_HASH", "参考資料", "BIM/CIM", "KTR", 120, "実務導線リンク集。"),
    MonitorSeed("中部：建設ICT総合サイト（入口）", "https://www.cbr.mlit.go.jp/kensetsu-ict/", "HTML_HASH", "参考資料", "ICT施工", "CBR", 120, "中部局ICT入口。"),
    MonitorSeed("中部：基準・要領類（局サイト）", "https://www.cbr.mlit.go.jp/kensetsu-ict/ict-kijun.html", "HTML_HASH", "参考資料", "ICT施工", "CBR", 120, "局視点の基準整理。"),
    MonitorSeed("東北：インフラDX（新着あり）", "https://www.thr.mlit.go.jp/Bumon/B00097/k00915/dxhp/dxhp.html", "HTML_HASH", "参考資料", "インフラDX", "THR", 120, "時系列新着あり。"),
    MonitorSeed("中部：インフラDX", "https://www.cbr.mlit.go.jp/kikaku/dx/infrastructure_dx.html", "HTML_HASH", "参考資料", "インフラDX", "CBR", 120, "中部局DX入口。"),
    MonitorSeed("中国：インフラDX（局ハブ）", "https://www.cgr.mlit.go.jp/infradx/index.html", "HTML_HASH", "参考資料", "インフラDX", "CGR", 120, "推進計画/会議リンク集。"),
    MonitorSeed("四国：インフラDX推進（局）", "https://www.skr.mlit.go.jp/kikaku/infraDX/", "HTML_HASH", "参考資料", "インフラDX", "SKR", 120, "四国局DX導線。"),
    MonitorSeed("九州：九州インフラDX推進室（入口）", "https://www.qsr.mlit.go.jp/infradx/index.html", "HTML_HASH", "参考資料", "インフラDX", "QSR", 120, "九州局DX入口。"),
]


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monitors (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          display_name TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE,
          watch_type TEXT NOT NULL,
          document_type TEXT,
          category TEXT,
          bureau_code TEXT,
          interval_min INTEGER NOT NULL DEFAULT 60,
          enabled INTEGER NOT NULL DEFAULT 1,
          note TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS monitor_state (
          monitor_id INTEGER PRIMARY KEY,
          last_checked_at TEXT,
          last_http_status INTEGER,
          last_error TEXT,
          fingerprint TEXT,
          etag TEXT,
          last_modified TEXT,
          content_length INTEGER,
          stable_count INTEGER NOT NULL DEFAULT 0,
          changed_count INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS change_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          monitor_id INTEGER NOT NULL,
          detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          change_type TEXT NOT NULL,
          prev_fingerprint TEXT,
          new_fingerprint TEXT,
          prev_etag TEXT,
          new_etag TEXT,
          prev_last_modified TEXT,
          new_last_modified TEXT,
          http_status INTEGER,
          summary TEXT,
          snapshot_path TEXT,
          notified INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_change_events_monitor_detected
          ON change_events(monitor_id, detected_at DESC);
        """
    )
    conn.commit()


def seed_defaults(conn: sqlite3.Connection) -> int:
    inserted = 0
    for s in SEEDS:
        before = conn.total_changes
        conn.execute(
            """
            INSERT INTO monitors (display_name, url, watch_type, document_type, category, bureau_code, interval_min, enabled, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(url) DO UPDATE SET
              display_name=excluded.display_name,
              watch_type=excluded.watch_type,
              document_type=excluded.document_type,
              category=excluded.category,
              bureau_code=excluded.bureau_code,
              interval_min=excluded.interval_min,
              note=excluded.note
            """,
            (s.display_name, s.url, s.watch_type, s.document_type, s.category, s.bureau_code, s.interval_min, s.note),
        )
        if conn.total_changes > before:
            inserted += 1

    conn.execute(
        """
        INSERT INTO monitor_state (monitor_id, last_checked_at)
        SELECT m.id, NULL
        FROM monitors m
        LEFT JOIN monitor_state s ON s.monitor_id = m.id
        WHERE s.monitor_id IS NULL
        """
    )
    conn.commit()
    return inserted


def normalize_html_for_hash(html: str) -> str:
    # Remove script/style/comment blocks, then trim whitespace.
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def http_head(url: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            headers = resp.headers
            return headers.get("ETag"), headers.get("Last-Modified"), getattr(resp, "status", None)
    except Exception:
        return None, None, None


def http_get(url: str) -> tuple[int, bytes, Optional[str], Optional[str], dict[str, str]]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        body = resp.read()
        headers = {k: v for k, v in resp.headers.items()}
        return getattr(resp, "status", 200), body, resp.headers.get_content_type(), resp.headers.get_content_charset(), headers


def fingerprint_for_monitor(url: str, watch_type: str) -> dict[str, Optional[str] | int]:
    etag, last_modified, head_status = (None, None, None)
    if watch_type in ("HTTP_META_ONLY", "HTTP_META_THEN_HASH"):
        etag, last_modified, head_status = http_head(url)

    if watch_type == "HTTP_META_ONLY":
        fp_src = f"etag={etag}|lm={last_modified}"
        return {
            "fingerprint": sha256_text(fp_src),
            "etag": etag,
            "last_modified": last_modified,
            "http_status": head_status or 0,
            "content_length": None,
            "summary": "meta-only check",
        }

    status, raw, content_type, charset, headers = http_get(url)
    etag = headers.get("ETag") or etag
    last_modified = headers.get("Last-Modified") or last_modified

    if content_type and "html" in content_type:
        text = raw.decode(charset or "utf-8", errors="ignore")
        norm = normalize_html_for_hash(text)
        fp = sha256_text(norm)
        summary = f"html bytes={len(raw)}"
    else:
        fp = hashlib.sha256(raw).hexdigest()
        summary = f"binary bytes={len(raw)}"

    if watch_type == "HTTP_META_THEN_HASH":
        fp = sha256_text(f"fp={fp}|etag={etag}|lm={last_modified}")

    return {
        "fingerprint": fp,
        "etag": etag,
        "last_modified": last_modified,
        "http_status": status,
        "content_length": len(raw),
        "summary": summary,
    }


def iter_targets(conn: sqlite3.Connection, limit: Optional[int] = None) -> Iterable[sqlite3.Row]:
    sql = """
    SELECT m.*, s.fingerprint AS prev_fingerprint, s.etag AS prev_etag, s.last_modified AS prev_last_modified
    FROM monitors m
    LEFT JOIN monitor_state s ON s.monitor_id = m.id
    WHERE m.enabled = 1
    ORDER BY m.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql)


def process_one(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    monitor_id = row["id"]
    try:
        res = fingerprint_for_monitor(row["url"], row["watch_type"])
        changed = (row["prev_fingerprint"] is not None) and (row["prev_fingerprint"] != res["fingerprint"])
        change_type = "content_changed" if changed else "stable"

        if changed:
            conn.execute(
                """
                INSERT INTO change_events (
                    monitor_id, detected_at, change_type,
                    prev_fingerprint, new_fingerprint,
                    prev_etag, new_etag,
                    prev_last_modified, new_last_modified,
                    http_status, summary, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    monitor_id,
                    utcnow_iso(),
                    change_type,
                    row["prev_fingerprint"],
                    res["fingerprint"],
                    row["prev_etag"],
                    res["etag"],
                    row["prev_last_modified"],
                    res["last_modified"],
                    res["http_status"],
                    res["summary"],
                ),
            )

        conn.execute(
            """
            INSERT INTO monitor_state (
                monitor_id, last_checked_at, last_http_status, last_error,
                fingerprint, etag, last_modified, content_length, stable_count, changed_count
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(monitor_id) DO UPDATE SET
                last_checked_at=excluded.last_checked_at,
                last_http_status=excluded.last_http_status,
                last_error=NULL,
                fingerprint=excluded.fingerprint,
                etag=excluded.etag,
                last_modified=excluded.last_modified,
                content_length=excluded.content_length,
                stable_count=CASE WHEN excluded.fingerprint != monitor_state.fingerprint THEN 0 ELSE monitor_state.stable_count + 1 END,
                changed_count=CASE WHEN excluded.fingerprint != monitor_state.fingerprint THEN monitor_state.changed_count + 1 ELSE monitor_state.changed_count END
            """,
            (
                monitor_id,
                utcnow_iso(),
                res["http_status"],
                res["fingerprint"],
                res["etag"],
                res["last_modified"],
                res["content_length"],
                1,
                0,
            ),
        )
        conn.commit()
        return f"OK   #{monitor_id} {row['display_name']}"
    except urllib.error.URLError as e:
        msg = f"{type(e).__name__}: {e.reason}" if getattr(e, "reason", None) else str(e)
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"

    conn.execute(
        """
        INSERT INTO change_events (monitor_id, detected_at, change_type, http_status, summary, notified)
        VALUES (?, ?, 'fetch_error', NULL, ?, 0)
        """,
        (monitor_id, utcnow_iso(), msg[:400]),
    )
    conn.execute(
        """
        INSERT INTO monitor_state (monitor_id, last_checked_at, last_http_status, last_error)
        VALUES (?, ?, NULL, ?)
        ON CONFLICT(monitor_id) DO UPDATE SET
          last_checked_at=excluded.last_checked_at,
          last_error=excluded.last_error
        """,
        (monitor_id, utcnow_iso(), msg[:400]),
    )
    conn.commit()
    return f"ERR  #{monitor_id} {row['display_name']} :: {msg}"


def run_once(conn: sqlite3.Connection, limit: Optional[int]) -> None:
    rows = list(iter_targets(conn, limit=limit))
    for row in rows:
        print(process_one(conn, row))


def list_monitors(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT m.id, m.display_name, m.watch_type, m.interval_min, m.url,
               s.last_checked_at, s.last_error
        FROM monitors m
        LEFT JOIN monitor_state s ON s.monitor_id = m.id
        ORDER BY m.id
        """
    ).fetchall()
    for r in rows:
        print(json.dumps(dict(r), ensure_ascii=False))


def run_daemon(conn: sqlite3.Connection, poll_sec: int, limit: Optional[int]) -> None:
    print(f"daemon started: poll={poll_sec}s db={DB_PATH}")
    while True:
        run_once(conn, limit=limit)
        time.sleep(poll_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple Web page watcher")
    parser.add_argument("--db", default=DB_PATH, help="sqlite db path")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="create tables")
    sub.add_parser("seed-defaults", help="upsert built-in monitor URLs")
    sub.add_parser("list-monitors", help="show monitors")

    run_once_p = sub.add_parser("run-once", help="execute checks once")
    run_once_p.add_argument("--limit", type=int, default=None)

    daemon_p = sub.add_parser("run-daemon", help="run repeatedly")
    daemon_p.add_argument("--poll-sec", type=int, default=300)
    daemon_p.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    conn = connect(args.db)

    if args.cmd == "init-db":
        init_db(conn)
        print("initialized")
    elif args.cmd == "seed-defaults":
        init_db(conn)
        count = seed_defaults(conn)
        print(f"seeded/upserted: {count}")
    elif args.cmd == "list-monitors":
        list_monitors(conn)
    elif args.cmd == "run-once":
        run_once(conn, limit=args.limit)
    elif args.cmd == "run-daemon":
        run_daemon(conn, poll_sec=args.poll_sec, limit=args.limit)


if __name__ == "__main__":
    main()
