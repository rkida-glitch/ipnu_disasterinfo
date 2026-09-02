# 防災情報モニター β2.1

GitHub Pages上でJavaScript外部ファイルの読み込み失敗が起きても影響しないよう、
設定とJavaScriptを index.html に統合しました。

## GitHubへ置くファイル
- index.html
- styles.css

既存の beta2 の `index.html` と `styles.css` を、この版の2ファイルで上書きしてください。
`app.js` と `config.js` は削除して構いません。

## 動作確認
公開後、ブラウザで Ctrl + F5 を押して強制再読み込みしてください。

正常時:
- 右上に19市町のデモ警報一覧
- 左下にメッセージ本文
- ヘッダー右に日付・時刻
- 左上にYouTube埋め込み
が表示されます。

右下の雨雲マップは次のPhaseで実データ接続予定です。
