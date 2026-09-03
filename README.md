# 石川県立看護大学 防災情報モニター β4

## 今回の修正点

### 1. 警報・注意報
旧 `warning/170000.json` の直接参照を廃止しました。

2026年5月28日以降の気象庁新体系に対応し、
GitHub Actions が気象庁防災情報XMLの
「気象警報・注意報（Ｒ０６）（集約通報） VPWS50」
を5分ごとに取得します。

取得した全国集約XMLから石川県19市町だけを抽出し、
`data/warnings.json` に保存します。
Web画面はこのJSONを読み込みます。

### 2. 今後の雨
- 背景地図を国土地理院「淡色地図」に変更
- 石川県全域にfitBounds
- JMA targetTimes の時刻をJSTとして処理
- 気象庁 `rasrf` 降水短時間予報タイルを表示
- 現在付近～6時間先を約5秒間隔でアニメーション

## GitHub上のファイル
必要ファイル：
- index.html
- styles.css
- data/warnings.json
- scripts/update_warnings.py
- .github/workflows/update-warnings.yml

## 最初の1回だけ必要な操作

GitHubのリポジトリで：

1. `Actions`
2. `Update JMA warnings`
3. `Run workflow`

を実行

成功すると `data/warnings.json` が自動更新され、その後は5分ごとに更新されます。

### Actionsがpushできない場合

Settings → Actions → General → Workflow permissions で
`Read and write permissions`
を許可してください。

## Pages
これまで通りGitHub Pagesは main / root で公開可能

## 注意
GitHub Actionsのscheduleは厳密に5分間隔で起動する保証はなく、
GitHub側の混雑により数分程度遅れることがあります。
