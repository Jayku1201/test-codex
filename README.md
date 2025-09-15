# Simple CRM 系統

本專案實作一個以 FastAPI 打造的簡易客戶關係管理（CRM）服務，提供客戶資料與互動紀錄的 CRUD API，方便中小型團隊快速建置客戶資料管理系統。

## 功能特色

- 客戶資料新增、查詢、修改與刪除
- 可依姓名、Email、電話或公司進行模糊搜尋
- 透過狀態與公司欄位進行篩選與排序
- 客戶互動紀錄管理（新增、查詢與總覽）
- SQLite 持久化儲存，測試時可自訂資料庫路徑

## 環境需求

- Python 3.9+
- pip 套件管理工具

## 安裝步驟

```bash
pip install -r requirements.txt
```

## 執行 API 服務

```bash
uvicorn app.main:app --reload
```

啟動後即可透過 `http://127.0.0.1:8000/docs` 進入自動產生的互動式 API 文件。

## 主要 API 一覽

| 方法 | 路徑 | 說明 |
| ---- | ---- | ---- |
| GET | `/health` | 服務健康檢查 |
| POST | `/customers` | 建立客戶資料 |
| GET | `/customers` | 取得客戶清單（支援搜尋、篩選、排序） |
| GET | `/customers/{customer_id}` | 取得特定客戶資料 |
| PUT | `/customers/{customer_id}` | 更新客戶資料 |
| DELETE | `/customers/{customer_id}` | 刪除客戶 |
| GET | `/customers/{customer_id}/interactions` | 查詢客戶互動紀錄 |
| POST | `/customers/{customer_id}/interactions` | 新增客戶互動紀錄 |
| GET | `/interactions` | 瀏覽全部互動紀錄 |

## 執行測試

```bash
pytest
```

測試會自動使用臨時 SQLite 資料庫，以確保環境乾淨且可重複執行。
