# EmePCRemote-updates

Eme PC Remote の自動アップデート配信用リポジトリです。

## 構成

`update/manifest.json` に最新版のバージョンと更新対象ファイルを記録し、
Eme PC Remote v0.3 以降がこのリポジトリから更新を取得します。

## セキュリティ

このリポジトリには次の個人設定を保存しません。

- `config.json`
- 接続用 token
- `EmePCRemote.log`

更新対象ファイルには SHA-256 を記録し、ダウンロード後に検証します。
