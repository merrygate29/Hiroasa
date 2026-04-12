#!/usr/bin/env python3
"""Simple web UI for the monitor_app SQLite watcher."""
from __future__ import annotations

import argparse
import html
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import monitor_app


DB_PATH = monitor_app.DB_PATH


CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; }
h1 { margin-bottom: 8px; }
small { color: #555; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 24px; }
th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; font-size: 14px; }
th { background: #f7f7f7; text-align: left; }
input, select, button { padding: 8px; margin: 4px 0; }
form.inline { display: inline-block; margin-right: 12px; }
section.card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.flash { padding: 10px; background: #eef7ff; border: 1px solid #b6ddff; border-radius: 6px; margin-bottom: 16px; }
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  {body}
</body>
</html>"""
    return doc.encode("utf-8")


def fetch_monitors() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT m.id, m.display_name, m.watch_type, m.document_type, m.category,
                   m.bureau_code, m.interval_min, m.url, s.last_checked_at, s.last_error
            FROM monitors m
            LEFT JOIN monitor_state s ON s.monitor_id = m.id
            WHERE m.enabled = 1
            ORDER BY m.id
            """
        ).fetchall()


def fetch_events(limit: int = 100) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT e.detected_at, e.change_type, e.summary, m.display_name, m.url
            FROM change_events e
            JOIN monitors m ON m.id = e.monitor_id
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def add_monitor(form: dict[str, list[str]]) -> None:
    display_name = (form.get("display_name", [""])[0]).strip()
    url = (form.get("url", [""])[0]).strip()
    watch_type = (form.get("watch_type", ["HTML_HASH"])[0]).strip()
    document_type = (form.get("document_type", [""])[0]).strip()
    category = (form.get("category", [""])[0]).strip()
    bureau_code = (form.get("bureau_code", [""])[0]).strip()
    interval_min_raw = (form.get("interval_min", ["60"])[0]).strip()

    if not display_name or not url:
        raise ValueError("表示名とURLは必須です。")

    try:
        interval_min = max(5, int(interval_min_raw))
    except ValueError as exc:
        raise ValueError("監視間隔は数字で入力してください。") from exc

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO monitors (display_name, url, watch_type, document_type, category, bureau_code, interval_min, enabled, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'Web UIで追加')
            ON CONFLICT(url) DO UPDATE SET
              display_name=excluded.display_name,
              watch_type=excluded.watch_type,
              document_type=excluded.document_type,
              category=excluded.category,
              bureau_code=excluded.bureau_code,
              interval_min=excluded.interval_min,
              enabled=1
            """,
            (display_name, url, watch_type, document_type, category, bureau_code, interval_min),
        )
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


def render_home(flash_message: str = "") -> bytes:
    monitors = fetch_monitors()
    events = fetch_events(limit=20)

    monitor_rows = "".join(
        f"<tr>"
        f"<td>{m['id']}</td>"
        f"<td>{html.escape(m['display_name'])}</td>"
        f"<td>{html.escape(m['watch_type'])}</td>"
        f"<td>{html.escape(m['category'] or '')}</td>"
        f"<td>{m['interval_min']}分</td>"
        f"<td><a href=\"{html.escape(m['url'])}\" target=\"_blank\">{html.escape(m['url'])}</a></td>"
        f"<td>{html.escape(m['last_checked_at'] or '-')}</td>"
        f"<td>{html.escape(m['last_error'] or '-')}</td>"
        f"</tr>"
        for m in monitors
    )

    event_rows = "".join(
        f"<tr>"
        f"<td>{html.escape(e['detected_at'] or '-')}</td>"
        f"<td>{html.escape(e['change_type'] or '-')}</td>"
        f"<td>{html.escape(e['display_name'] or '-')}</td>"
        f"<td>{html.escape(e['summary'] or '-')}</td>"
        f"</tr>"
        for e in events
    )

    flash = f"<div class='flash'>{html.escape(flash_message)}</div>" if flash_message else ""

    body = f"""
    <h1>監視Webサイト</h1>
    <small>ブラウザからURL登録・監視実行・履歴確認ができます。</small>
    {flash}

    <section class=\"card\">
      <h2>操作</h2>
      <form class=\"inline\" method=\"post\" action=\"/seed\">
        <button type=\"submit\">45件の初期URLを投入</button>
      </form>
      <form class=\"inline\" method=\"post\" action=\"/run\">
        <input type=\"number\" name=\"limit\" value=\"5\" min=\"1\" style=\"width:80px\"> 件だけ監視
        <button type=\"submit\">監視を実行</button>
      </form>
    </section>

    <section class=\"card\">
      <h2>URLを追加</h2>
      <form method=\"post\" action=\"/add\">
        <div><input name=\"display_name\" placeholder=\"表示名\" style=\"width:320px\" required></div>
        <div><input name=\"url\" type=\"url\" placeholder=\"https://...\" style=\"width:520px\" required></div>
        <div>
          <select name=\"watch_type\">
            <option value=\"HTML_HASH\">HTML_HASH</option>
            <option value=\"HTTP_META_THEN_HASH\">HTTP_META_THEN_HASH</option>
            <option value=\"HTTP_META_ONLY\">HTTP_META_ONLY</option>
          </select>
          <input name=\"document_type\" placeholder=\"DocumentType\" style=\"width:140px\">
          <input name=\"category\" placeholder=\"Category\" style=\"width:140px\">
          <input name=\"bureau_code\" placeholder=\"部局コード\" style=\"width:120px\">
          <input name=\"interval_min\" type=\"number\" min=\"5\" value=\"60\" style=\"width:90px\"> 分
        </div>
        <button type=\"submit\">追加 / 更新</button>
      </form>
    </section>

    <section class=\"card\">
      <h2>監視対象 ({len(monitors)}件)</h2>
      <table>
        <thead><tr><th>ID</th><th>表示名</th><th>方式</th><th>カテゴリ</th><th>間隔</th><th>URL</th><th>最終確認</th><th>最終エラー</th></tr></thead>
        <tbody>{monitor_rows}</tbody>
      </table>
    </section>

    <section class=\"card\">
      <h2>最新イベント (20件)</h2>
      <table>
        <thead><tr><th>時刻</th><th>種別</th><th>対象</th><th>概要</th></tr></thead>
        <tbody>{event_rows}</tbody>
      </table>
    </section>
    """
    return page("監視Webサイト", body)


class Handler(BaseHTTPRequestHandler):
    def _send_html(self, content: bytes, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _redirect(self, to: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", to)
        self.end_headers()

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8", errors="ignore")
        return parse_qs(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(render_home())
            return
        self._send_html(page("Not Found", "<h1>404 Not Found</h1>"), status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        form = self._read_form()
        try:
            if path == "/seed":
                with get_conn() as conn:
                    monitor_app.init_db(conn)
                    count = monitor_app.seed_defaults(conn)
                self._send_html(render_home(f"初期データを投入しました（変更件数: {count}）。"))
                return
            if path == "/run":
                limit_raw = (form.get("limit", ["5"])[0]).strip()
                limit = max(1, int(limit_raw))
                with get_conn() as conn:
                    for row in list(monitor_app.iter_targets(conn, limit=limit)):
                        monitor_app.process_one(conn, row)
                self._send_html(render_home(f"監視を実行しました（対象: {limit}件）。"))
                return
            if path == "/add":
                add_monitor(form)
                self._send_html(render_home("URLを追加/更新しました。"))
                return
            self._redirect("/")
        except Exception as exc:  # noqa: BLE001
            self._send_html(render_home(f"エラー: {exc}"), status=HTTPStatus.BAD_REQUEST)


def main() -> None:
    global DB_PATH
    parser = argparse.ArgumentParser(description="Web UI for monitor_app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    DB_PATH = args.db

    with get_conn() as conn:
        monitor_app.init_db(conn)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Web UI started: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
