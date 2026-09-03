# β4.4 Fixed Map hotfix

雨雲マップを端末依存しにくい構成に変更しました。

## 変更点
- 表示中心を [36.78, 136.78] に固定
- Zoomを 8 に固定
- `fitBounds()` を廃止
- ドラッグ、ホイールズーム、タッチズーム等を無効化
- base / rain / boundary を専用paneに分離
- z-indexを固定
- 雨雲レイヤーは Zoom 8 のみ要求
- opacityを0.90へ変更
- resize後も中心・Zoomを強制的に再設定

## GitHubで差し替えるもの
`index.html` のみでOKです。

既存の `styles.css`、`data/`、`scripts/`、`.github/workflows/` はそのまま使ってください。

更新後は `Ctrl + F5` で強制再読み込みしてください。
