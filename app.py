import re
from typing import Any, Dict, Tuple
from flask import Flask, jsonify, request

from config import TOP_N
from line_notifier import LineNotifier
from shopee_api import ShopeeAffiliateClient

app = Flask(__name__)
shopee_client = ShopeeAffiliateClient()
line_notifier = LineNotifier()

HELP_MESSAGE = (
    "🤖 【豪爺蝦皮熱銷排行助理】使用說明\n"
    "━━━━━━━━━━━━━━\n"
    "您可以直接傳送以下指令給我，我會立刻抓取最新熱銷榜並附上您的專屬分潤連結：\n\n"
    "1️⃣ 查詢全站熱銷（可指定 1~50 個）：\n"
    "   • 輸入「熱銷」或「10」👉 全站 Top 10\n"
    "   • 輸入「30」或「熱銷 30」👉 全站 Top 30\n"
    "   • 輸入「50」或「給我50個」👉 全站 Top 50\n\n"
    "2️⃣ 查詢指定商品/分類熱銷＋數量：\n"
    "   • 輸入「藍牙耳機」👉 藍牙耳機 Top 10\n"
    "   • 輸入「行動電源 20」👉 行動電源 Top 20\n"
    "   • 輸入「收納 50」👉 收納 Top 50\n\n"
    "👇 您也可以直接點擊下方快捷按鈕查詢！"
)

GENERIC_HOT_WORDS = {
    "熱銷",
    "排行榜",
    "排行",
    "熱銷榜",
    "熱賣",
    "最新",
    "最新狀況",
    "全站",
    "給我",
    "我要",
    "查詢",
    "搜尋",
    "蝦皮",
    "top",
}


def parse_line_command(raw_text: str) -> Tuple[bool, str, int]:
    """
    解析使用者在 LINE 輸入的文字指令
    :return: (is_help, keyword, limit)
    """
    text = (raw_text or "").strip()
    if not text or text.lower() in {"help", "?", "？", "幫助", "指令", "說明", "選單"}:
        return True, "", TOP_N

    limit = TOP_N

    # 1. 若整串就是純數字 (例如 "10", "50")
    if re.fullmatch(r"\d+", text):
        limit = min(max(int(text), 1), 50)
        return False, "", limit

    # 2. 匹配「前50名 / 50個 / 50筆 / 50件 / Top 50」
    m_unit = re.search(r"(?:前|top\s*)?(\d+)\s*(?:個|名|筆|件|項)", text, flags=re.I)
    if m_unit:
        limit = min(max(int(m_unit.group(1)), 1), 50)
        text = (text[: m_unit.start()] + " " + text[m_unit.end() :]).strip()
    else:
        # 3. 匹配結尾獨立數字 (例如 "熱銷 50", "藍牙耳機 20", "3C 10")
        m_tail = re.search(r"(?:\s+|(?<=[a-zA-Z\u4e00-\u9fff]))(\d{1,2})$", text)
        if m_tail and not text.upper().endswith("3C"):
            limit = min(max(int(m_tail.group(1)), 1), 50)
            text = text[: m_tail.start()].strip()

    # 清理常見贅字，判斷剩下的是否為特定關鍵字
    tokens = [t for t in re.split(r"\s+", text) if t]
    filtered_tokens = []
    for tok in tokens:
        cleaned = re.sub(r"^(給我|我要|查詢|搜尋|看看|最新|蝦皮)+", "", tok)
        cleaned = re.sub(r"(熱銷排行榜|熱銷榜|排行榜|熱銷|排行|最新狀況|狀況)$", "", cleaned)
        if cleaned and cleaned.lower() not in GENERIC_HOT_WORDS:
            filtered_tokens.append(cleaned)

    keyword = " ".join(filtered_tokens).strip()
    return False, keyword, limit


@app.route("/", methods=["GET"])
def index() -> Any:
    return jsonify(
        {
            "status": "ok",
            "service": "Shopee Affiliate Ranking LINE Bot",
            "message": "Webhook server is running. Set LINE Webhook URL to /callback",
        }
    )


@app.route("/cron", methods=["GET", "POST"])
def trigger_daily_cron() -> Any:
    """可供雲端排程器呼叫的每日主動推播端點"""
    products = shopee_client.fetch_top_products(keyword="", limit=TOP_N)
    line_notifier.send_ranking_report(f"🔥 蝦皮全站熱銷 Top {len(products)}", products)
    return jsonify({"status": "pushed", "count": len(products)})


@app.route("/callback", methods=["POST"])
@app.route("/webhook", methods=["POST"])
def line_webhook() -> Any:
    """接收 LINE Messaging API Webhook 事件並即時回覆排行榜"""
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    events = body.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        reply_token = event.get("replyToken", "")
        user_id = event.get("source", {}).get("userId", "")
        user_text = message.get("text", "")

        # 若使用者直接貼上蝦皮商品網址，自動幫他轉換成專屬分潤短網址
        url_match = re.search(
            r"(https?://(?:[\w.-]*shopee\.tw|[\w.-]*shp\.ee)/[^\s]+)",
            user_text,
            flags=re.I,
        )
        if url_match:
            raw_url = url_match.group(1)
            clean_url = raw_url.split("?")[0]
            short_aff = shopee_client.build_affiliate_link(clean_url, sub_id="line_custom")
            reply_msg = (
                "✅ 已為您轉換成專屬分潤短網址：\n"
                f"👉 {short_aff}\n\n"
                f"（已綁定推廣者編號：{shopee_client.affiliate_id}）"
            )
            line_notifier.reply_text(reply_token, reply_msg)
            continue

        is_help, keyword, limit = parse_line_command(user_text)
        if is_help:
            line_notifier.reply_text(reply_token, HELP_MESSAGE)
            continue

        title = (
            f"🔥 蝦皮【{keyword}】熱銷 Top {limit}"
            if keyword
            else f"🔥 蝦皮全站熱銷 Top {limit}"
        )
        print(f"📩 收到 LINE 指令: '{user_text}' -> 關鍵字='{keyword or '全站'}', 數量={limit}")

        products = shopee_client.fetch_top_products(keyword=keyword, limit=limit)
        line_notifier.reply_ranking_report(
            reply_token=reply_token,
            title=title,
            products=products,
            user_id=user_id,
        )

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
