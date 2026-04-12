# Hiroasa

だれでも使えるように、**起動すると自動でブラウザが開く** 監視Webサイトにしました。

## いちばん簡単な使い方

### Windows
`start_web.bat` をダブルクリック。

### Mac / Linux
```bash
./start_web.sh
```

または共通で:
```bash
python3 run_web.py
```

起動するとブラウザで以下が開きます。
- <http://127.0.0.1:8000>

## 使い方（画面）

- 初回起動時は45件の監視URLを自動投入
- URLの追加/更新
- 件数指定で監視実行
- 最新イベント履歴の確認

## 停止

ターミナルで `Ctrl + C`。

## 補足（上級者向け）

自動でブラウザを開きたくない場合:
```bash
python3 web_app.py --no-open-browser
```

SQLiteファイルは `watcher.db` です。
