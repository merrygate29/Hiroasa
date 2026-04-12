# Hiroasa

Webページ更新監視の最小アプリです（SQLite + 標準ライブラリのみ）。

## セットアップ

```bash
python3 monitor_app.py init-db
python3 monitor_app.py seed-defaults
```

## 使い方

### 監視対象一覧
```bash
python3 monitor_app.py list-monitors
```

### 一回だけ監視実行
```bash
python3 monitor_app.py run-once
```

テスト用途で件数を絞る場合:
```bash
python3 monitor_app.py run-once --limit 5
```

### 常駐実行（ポーリング）
```bash
python3 monitor_app.py run-daemon --poll-sec 300
```

## 収集データ

- `monitors`: 監視URL設定
- `monitor_state`: 最新状態（fingerprint / etag / last-modified / エラー）
- `change_events`: 変更・取得失敗イベント履歴

## 監視方式

- `HTML_HASH`: HTMLを正規化してハッシュ比較
- `HTTP_META_THEN_HASH`: HEADでメタ情報確認 + GET内容のハッシュ比較
- `HTTP_META_ONLY`: ETag/Last-Modifiedのみで疎監視

## 備考

- 初回実行はベースライン作成となり、通常は変更通知を出しません。
- 政府サイト側の構成変更により、一時的な誤検知や取得失敗が発生することがあります。
