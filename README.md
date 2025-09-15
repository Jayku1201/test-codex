# Simple CRM API

這是一個以 FastAPI 實作的簡易客戶資料管理系統（CRM）。系統提供客戶、互動紀錄、商機與待辦任務的 CRUD 操作，以及簡單的分析摘要，可作為中小型團隊追蹤銷售流程與客戶關係的起點。

## 功能特色

- ✨ **客戶管理**：建立、查詢、更新、刪除客戶，並支援依狀態、標籤與關鍵字搜尋。
- 🗒️ **互動紀錄**：記錄與客戶的電話、會議或備註，掌握歷史紀錄。
- 💼 **商機追蹤**：針對客戶新增商機、更新狀態與金額，掌握銷售進度。
- ✅ **待辦任務**：建立跟進任務，設定到期日與狀態，確保行動項目不遺漏。
- 📊 **分析摘要**：取得客戶總數、Lead 數量、商機與逾期任務等概況。
- ⚙️ **RESTful API**：採用 FastAPI，內建互動式文件（Swagger UI / ReDoc）。

## 快速開始

### 1. 安裝相依套件

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 啟動開發伺服器

```bash
uvicorn app.main:app --reload
```

伺服器預設會在 `http://127.0.0.1:8000` 運行，並自動建立 `crm.db` SQLite 資料庫。

可透過以下網址瀏覽互動式 API 文件：

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

### 3. 執行測試

```bash
pytest
```

測試套件會以記憶體資料庫執行，涵蓋客戶、互動、商機、任務與分析摘要的主要流程。

## 主要 API

| Method | Path | 描述 |
| --- | --- | --- |
| `GET` | `/customers` | 列出客戶並可依狀態、標籤、關鍵字過濾 |
| `POST` | `/customers` | 新增客戶 |
| `GET` | `/customers/{customer_id}` | 取得單一客戶（含互動、商機、任務） |
| `PUT` | `/customers/{customer_id}` | 更新客戶資料 |
| `DELETE` | `/customers/{customer_id}` | 刪除客戶 |
| `GET` | `/customers/{id}/interactions` | 取得客戶互動列表 |
| `POST` | `/customers/{id}/interactions` | 建立互動紀錄 |
| `PUT` | `/customers/{id}/interactions/{interaction_id}` | 更新互動 |
| `DELETE` | `/customers/{id}/interactions/{interaction_id}` | 刪除互動 |
| `GET` | `/customers/{id}/opportunities` | 取得客戶商機列表 |
| `POST` | `/customers/{id}/opportunities` | 建立商機 |
| `PUT` | `/customers/{id}/opportunities/{opportunity_id}` | 更新商機 |
| `DELETE` | `/customers/{id}/opportunities/{opportunity_id}` | 刪除商機 |
| `GET` | `/customers/{id}/tasks` | 取得客戶任務列表 |
| `POST` | `/customers/{id}/tasks` | 建立任務 |
| `PUT` | `/customers/{id}/tasks/{task_id}` | 更新任務 |
| `DELETE` | `/customers/{id}/tasks/{task_id}` | 刪除任務 |
| `GET` | `/analytics/overview` | 取得 CRM 分析摘要 |

## 設定

- 預設資料庫為 `sqlite:///./crm.db`。可透過環境變數 `CRM_DATABASE_URL` 指定其他資料庫連線字串。
- 服務啟動時會自動建立所需資料表。

## 未來可延伸方向

- 客製化報表與更豐富的統計資料。
- 權限管理、使用者登入與審計紀錄。
- 與外部服務（如電子郵件、行事曆）整合。
- 加入前端介面或行動裝置 App。

歡迎依需求調整與擴充本專案！
