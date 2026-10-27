import os
from pathlib import Path

# 載入本地 .env 檔案（支援 python-dotenv，若未安裝則使用內建輕量解析器）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

# ==========================================
# 憑證與 API 金鑰設定
# ==========================================
# 您的蝦皮分潤推廣者編號 (Affiliate ID)
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "16378530039").strip()

# 選填：若未來開通蝦皮 Open API 可填入（未開通時會自動使用免 API 金鑰模式 + 推廣者編號）
SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID", "").strip()
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET", "").strip()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
# 支援單一或多個 User ID（以逗號分隔）
LINE_USER_IDS = [
    uid.strip()
    for uid in os.getenv("LINE_USER_ID", "").split(",")
    if uid.strip()
]

# 台灣蝦皮分潤 Open API GraphQL 端點
SHOPEE_GRAPHQL_ENDPOINT = "https://open-api.affiliate.shopee.tw/graphql"

# 預設每個排行榜抓取的商品數量（支援 1 ~ 50）
TOP_N = min(max(int(os.getenv("TOP_N", "10")), 1), 50)

# ==========================================
# 蝦皮排序與清單類型常數說明
# ==========================================
# sort_type (排序方式):
#   1 = RELEVANCE_DESC  (相關度最高)
#   2 = ITEM_SOLD_DESC  (最熱銷 / 銷量由高到低)  <-- 熱銷排行榜推薦使用
#   3 = PRICE_DESC      (價格由高到低)
#   4 = PRICE_ASC       (價格由低到高)
#   5 = COMMISSION_DESC (分潤佣金由高到低)
#
# list_type (清單類型):
#   0 = ALL                (全部分潤商品)
#   1 = HIGHEST_COMMISSION (高佣金精選商品)
#   2 = TOP_PERFORMING     (熱銷表現最佳精選商品)

# ==========================================
# 每日搜尋的排行榜清單設定
# ==========================================
# 您可以在下方自由新增、修改或取消註解想要每天追蹤的關鍵字排行榜！
SEARCH_CONFIGS = [
    {
        "title": "🔥 蝦皮全站熱銷排行榜",
        "keyword": "",       # 空字串代表不限關鍵字（全站搜尋）
        "list_type": 0,      # 0: 全部商品 (若想看官方精選熱銷可改為 2)
        "sort_type": 2,      # 2: 依銷量由高到低排序
    },
    # --- 若想同時追蹤特定分類或關鍵字，可取消下方註解 ---
    # {
    #     "title": "📱 3C 數位熱銷排行榜",
    #     "keyword": "3C",
    #     "list_type": 0,
    #     "sort_type": 2,
    # },
    # {
    #     "title": "🏠 居家生活熱銷排行榜",
    #     "keyword": "收納 居家",
    #     "list_type": 0,
    #     "sort_type": 2,
    # },
    # {
    #     "title": "💄 美妝保養熱銷排行榜",
    #     "keyword": "保養 美妝",
    #     "list_type": 0,
    #     "sort_type": 2,
    # },
]
