# Hiroasa

ブラウザで使える **Webページ更新監視サイト** です。  
URLを画面から登録し、監視実行と変更履歴の確認ができます。

## 起動方法（3ステップ）

```bash
python3 web_app.py --host 127.0.0.1 --port 8000
```

ブラウザで以下を開きます。

- <http://127.0.0.1:8000>

## 画面でできること

- 初期URL（45件）を投入
- 監視対象URLの追加/更新
- 件数指定で監視実行
- 最新イベント履歴の確認

## CLIを使う場合（任意）

Web画面を使わず、コマンドだけで操作することもできます。

```bash
python3 monitor_app.py init-db
python3 monitor_app.py seed-defaults
python3 monitor_app.py list-monitors
python3 monitor_app.py run-once --limit 5
```

## 監視方式

- `HTML_HASH`: HTMLを正規化してハッシュ比較
- `HTTP_META_THEN_HASH`: HEADメタ情報 + GET内容のハッシュ比較
- `HTTP_META_ONLY`: ETag/Last-Modifiedのみで疎監視

## 保存されるデータ

- `monitors`: 監視設定
- `monitor_state`: 最新状態
- `change_events`: 変更/取得失敗イベント

SQLiteファイルは `watcher.db` です。
