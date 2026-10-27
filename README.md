# 🛒 蝦皮每日熱銷排行榜 LINE 機器人（支援定時推播 + LINE 傳訊即時查詢）

自動搜尋台灣蝦皮熱銷商品排行榜、自動綁定您的**蝦皮分潤推廣者編號 (`16378530039`)**，並支援：
1. **每日早上 10:00 自動推播**（透過 GitHub Actions 雲端免費定時執行）
2. **在 LINE 隨時傳訊息即時查詢**（透過 [`app.py`](file:///c:/Users/user/Desktop/蝦皮機器人/app.py) Webhook 伺服器，支援指定 `10`～`50` 個數量與自訂關鍵字，並附帶底部快捷按鈕！）

---

## 💬 LINE 對話指令一覽（傳訊息給機器人即可觸發）

| 您在 LINE 輸入的內容 | 機器人回覆內容 |
| :--- | :--- |
| **`熱銷`** 或 **`10`** | 最新全站熱銷 **Top 10** |
| **`30`** 或 **`熱銷 30`** | 最新全站熱銷 **Top 30** |
| **`50`** 或 **`給我50個`** | 最新全站熱銷 **Top 50** |
| **`藍牙耳機`** | 「藍牙耳機」熱銷 **Top 10** |
| **`行動電源 20`** | 「行動電源」熱銷 **Top 20** |
| **`收納 50`** | 「收納」熱銷 **Top 50** |
| **`幫助`** 或 **`指令`** | 顯示指令說明與底部快捷按鈕選單 |

---

## ☁️ 步驟一：上傳至 GitHub 並開啟「每日早上 10:00 自動推播」

1. 登入 [GitHub](https://github.com/)，點擊右上角 **`+`** -> **`New repository`**，建立一個新儲存庫（例如命名為 `shopee-line-bot`）。
2. 將 `c:\Users\user\Desktop\蝦皮機器人` 資料夾內的檔案上傳至該儲存庫（`.env` 已被 `.gitignore` 保護不會上傳）。
3. 進入 GitHub 儲存庫上方的 **`Settings`** -> 左側 **`Secrets and variables`** -> **`Actions`** -> 點擊 **`New repository secret`**，新增以下 2 個金鑰（分潤推廣者編號 `16378530039` 已預設寫在程式中）：
   - `LINE_CHANNEL_ACCESS_TOKEN`：您的 LINE Channel Access Token
   - `LINE_USER_ID`：您的 LINE User ID
4. 點選上方 **`Actions`** 頁籤，即可看到 **`Daily Shopee Ranking LINE Bot`**，每天台灣時間早上 10:00 會自動執行！

---

## ⚡ 步驟二：開啟「在 LINE 傳訊即時回覆」功能（免費雲端 Vercel 部署）

因為 GitHub Actions 只有定時鬧鐘功能，若要讓 LINE 隨時傳訊都能 24 小時秒回，只需將同一個 GitHub 儲存庫連上免費的 **Vercel**：

1. 使用您的 GitHub 帳號登入 [Vercel.com](https://vercel.com/)。
2. 點擊 **`Add New...`** -> **`Project`** -> 選擇剛剛建立的 `shopee-line-bot` 儲存庫 -> 點擊 **`Import`**。
3. 展開 **`Environment Variables`**，填入：
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_USER_ID`
4. 點擊 **`Deploy`**，等待約 30 秒部署完成後，Vercel 會給您一個專屬網址（例如 `https://shopee-line-bot-xxx.vercel.app`）。
5. 回到您的 **[LINE Developers Console (Messaging API 頁籤)](https://developers.line.biz/console/channel/2009598457/messaging-api)**：
   - 找到 **`Webhook URL`**，填入：`https://您的Vercel網址.vercel.app/callback`
   - 點擊 **`Update`** 並打開下方的 **`Use webhook`** 開關！
   - （選填）在 LINE Official Account Manager 中將「自動回應訊息」關閉，並開啟「Webhook」。
6. 完成！現在您在 LINE 隨時傳送 `50`、`熱銷 30` 或點選對話框底部的快捷按鈕，機器人就會隨時給您最新排行榜！
