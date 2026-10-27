from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
import requests

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_IDS

LINE_PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"
LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
TW_TZ = timezone(timedelta(hours=8))


class LineNotifier:
    """LINE Messaging API 推播與即時回覆客戶端（支援 1~50 筆商品、多組輪播卡片、文字分段與快捷按鈕）"""

    def __init__(
        self,
        channel_access_token: str = LINE_CHANNEL_ACCESS_TOKEN,
        user_ids: List[str] = None,
    ):
        self.channel_access_token = channel_access_token
        self.user_ids = user_ids if user_ids is not None else LINE_USER_IDS

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}",
        }

    @staticmethod
    def build_quick_reply() -> Dict[str, Any]:
        """建立 LINE 對話框底部的快捷按鈕（點一下即可查詢不同數量或分類）"""
        options = [
            ("🔥 熱銷 Top 10", "熱銷 10"),
            ("🔥 熱銷 Top 30", "熱銷 30"),
            ("🔥 熱銷 Top 50", "熱銷 50"),
            ("📱 3C 熱銷 10", "3C 10"),
            ("🏠 居家收納 10", "收納 10"),
            ("💄 美妝保養 10", "保養 10"),
            ("💡 指令說明", "幫助"),
        ]
        return {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "message",
                        "label": label,
                        "text": text,
                    },
                }
                for label, text in options
            ]
        }

    @staticmethod
    def build_flex_carousel(title: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """建立單組 LINE Flex Message 輪播圖文卡片（最多 10 張卡片）"""
        bubbles = []
        for item in products[:10]:
            rank = item["rank"]
            name = item["name"][:60]
            sales_txt = (
                item["sales_display"]
                if str(item["sales_display"]).startswith("熱銷")
                else f"已售 {item['sales_display']}"
            )
            share_text = (
                f"🔥 蝦皮熱銷 TOP {rank}：{item['name']}\n"
                f"💰 優惠價：{item['price_display']}（{sales_txt}）\n"
                f"👉 專屬搶購連結：{item['offer_link']}"
            )[:300]

            bubble = {
                "type": "bubble",
                "size": "mega",
                "hero": {
                    "type": "image",
                    "url": item["image_url"],
                    "size": "full",
                    "aspectRatio": "1:1",
                    "aspectMode": "cover",
                    "action": {
                        "type": "uri",
                        "uri": item["offer_link"],
                    },
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "paddingAll": "16px",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "alignItems": "center",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "vertical",
                                    "backgroundColor": "#EE4D2D",
                                    "cornerRadius": "4px",
                                    "paddingStart": "8px",
                                    "paddingEnd": "8px",
                                    "paddingTop": "2px",
                                    "paddingBottom": "2px",
                                    "flex": 0,
                                    "contents": [
                                        {
                                            "type": "text",
                                            "text": f"TOP {rank}",
                                            "color": "#FFFFFF",
                                            "size": "xs",
                                            "weight": "bold",
                                        }
                                    ],
                                },
                                {
                                    "type": "text",
                                    "text": f"🔥 {sales_txt}",
                                    "size": "xs",
                                    "color": "#666666",
                                    "align": "end",
                                },
                            ],
                        },
                        {
                            "type": "text",
                            "text": name,
                            "weight": "bold",
                            "size": "md",
                            "wrap": True,
                            "maxLines": 2,
                            "margin": "sm",
                        },
                        {
                            "type": "text",
                            "text": f"⭐ {item['rating_display']} ｜ 🏪 {item['shop_name'][:18]}",
                            "size": "xs",
                            "color": "#888888",
                        },
                        {
                            "type": "text",
                            "text": item["price_display"],
                            "weight": "bold",
                            "size": "xl",
                            "color": "#EE4D2D",
                            "margin": "sm",
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#FFF5F2",
                            "cornerRadius": "6px",
                            "paddingAll": "8px",
                            "margin": "md",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"💰 {item['commission_rate_display']} ｜ 預估分潤 {item['commission_display']}",
                                    "size": "xs",
                                    "color": "#D03E1E",
                                    "weight": "bold",
                                }
                            ],
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "paddingTop": "0px",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#EE4D2D",
                            "height": "sm",
                            "action": {
                                "type": "uri",
                                "label": "🔗 開啟分潤推廣連結",
                                "uri": item["offer_link"],
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "clipboard",
                                "label": "📋 一鍵複製推廣文案",
                                "clipboardText": share_text,
                            },
                        },
                    ],
                },
            }
            bubbles.append(bubble)

        today_str = datetime.now(TW_TZ).strftime("%Y/%m/%d")
        first_rank = products[0]["rank"] if products else 1
        last_rank = products[len(bubbles) - 1]["rank"] if bubbles else 1
        return {
            "type": "flex",
            "altText": f"{title} ({today_str}) 第 {first_rank}~{last_rank} 名",
            "contents": {
                "type": "carousel",
                "contents": bubbles,
            },
        }

    @staticmethod
    def build_text_summary(title: str, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """建立單則純文字排行榜清單（供終端機預覽或 25 筆以內使用）"""
        today_str = datetime.now(TW_TZ).strftime("%Y/%m/%d")
        first_rank = products[0]["rank"] if products else 1
        last_rank = products[-1]["rank"] if products else 1
        range_label = f" (第 {first_rank}~{last_rank} 名)" if len(products) > 1 else ""
        lines = [
            f"{title}{range_label}",
            f"📅 統計日期：{today_str}",
            "━━━━━━━━━━━━━━",
        ]
        for item in products:
            short_name = (
                item["name"][:28] + "..."
                if len(item["name"]) > 28
                else item["name"]
            )
            sales_txt = (
                item["sales_display"]
                if str(item["sales_display"]).startswith("熱銷")
                else f"已售 {item['sales_display']}"
            )
            lines.append(
                f"🏅 第 {item['rank']} 名：{short_name}\n"
                f"   💵 {item['price_display']} ｜ 🔥 {sales_txt}\n"
                f"   💰 {item['commission_rate_display']} (預估約 {item['commission_display']})\n"
                f"   🔗 {item['offer_link']}"
            )

        text_content = "\n\n".join(lines)
        if len(text_content) > 4900:
            text_content = text_content[:4900] + "\n...(內容過長已截斷)"

        return {
            "type": "text",
            "text": text_content,
        }

    def build_report_messages(self, title: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        根據商品數量 (1~50 筆) 自動組合最佳的 LINE 訊息陣列（LINE 單次 API 上限為 5 則訊息氣泡）：
        - 文字清單每 25 筆分為 1 則訊息（避免超過 LINE 單則 5000 字上限）
        - 剩餘氣泡空間（最多 3 組，共 30 張圖文卡片）自動放入 Flex 輪播圖文卡片
        - 最後一則訊息自動附帶 Quick Reply 快捷按鈕
        """
        # 1. 先將純文字清單以每 20 筆切分，確保絕不超過單則 5000 字上限
        text_chunks: List[Dict[str, Any]] = []
        chunk_size = 20
        for i in range(0, len(products), chunk_size):
            sub_items = products[i : i + chunk_size]
            text_chunks.append(self.build_text_summary(title, sub_items))

        # LINE 單次最多 5 則訊息，計算可放幾組 Flex 輪播卡片 (每組 10 張卡片)
        max_flex_count = max(1, 5 - len(text_chunks))
        flex_messages: List[Dict[str, Any]] = []
        for i in range(0, min(len(products), max_flex_count * 10), 10):
            sub_items = products[i : i + 10]
            flex_messages.append(self.build_flex_carousel(title, sub_items))

        messages = (flex_messages + text_chunks)[:5]
        if messages:
            messages[-1]["quickReply"] = self.build_quick_reply()
        return messages

    def send_ranking_report(self, title: str, products: List[Dict[str, Any]]) -> None:
        """主動推播 (Push API) 排行榜給所有設定的 LINE_USER_ID"""
        if not self.channel_access_token or not self.user_ids:
            raise ValueError(
                "尚未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID！請檢查 .env 或 GitHub Secrets 設定。"
            )

        if not products:
            print(f"⚠️ [{title}] 未抓取到任何商品，略過發送。")
            return

        messages = self.build_report_messages(title, products)
        text_only_messages = [m for m in messages if m.get("type") == "text"]

        for uid in self.user_ids:
            payload = {
                "to": uid,
                "messages": messages,
            }
            resp = requests.post(
                LINE_PUSH_ENDPOINT,
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            if resp.status_code == 200:
                print(
                    f"✅ 已成功推播 [{title}] (共 {len(products)} 筆商品) 至 LINE ({uid[:8]}...)"
                )
            else:
                print(
                    f"⚠️ Flex 推播回傳狀態碼 {resp.status_code} ({resp.text})，嘗試改以純文字推播..."
                )
                fallback_payload = {
                    "to": uid,
                    "messages": text_only_messages[:5],
                }
                fallback_resp = requests.post(
                    LINE_PUSH_ENDPOINT,
                    headers=self._headers(),
                    json=fallback_payload,
                    timeout=20,
                )
                fallback_resp.raise_for_status()
                print(f"✅ 已成功以純文字推播 [{title}] 至 LINE ({uid[:8]}...)")

    def reply_ranking_report(
        self, reply_token: str, title: str, products: List[Dict[str, Any]], user_id: str = ""
    ) -> None:
        """
        被動回覆 (Reply API，完全免費不扣推播額度)：
        當使用者在 LINE 傳訊給機器人時，立即回覆最新排行榜；若 replyToken 逾時則自動切換為 Push API。
        """
        if not products:
            self.reply_text(
                reply_token,
                f"⚠️ 找不到符合【{title}】的商品，請換個關鍵字試試看！",
            )
            return

        messages = self.build_report_messages(title, products)
        payload = {
            "replyToken": reply_token,
            "messages": messages,
        }
        resp = requests.post(
            LINE_REPLY_ENDPOINT,
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        if resp.status_code == 200:
            print(f"✅ 已透過 Reply API 即時回覆 [{title}] (共 {len(products)} 筆)")
            return

        # 若因抓取 50 筆耗時超過 replyToken 時效，自動使用 Push API 補發給該使用者
        print(f"ℹ️ Reply API 回傳 {resp.status_code}，自動改用 Push API 傳送...")
        target_uid = user_id or (self.user_ids[0] if self.user_ids else "")
        if target_uid:
            push_payload = {"to": target_uid, "messages": messages}
            requests.post(
                LINE_PUSH_ENDPOINT,
                headers=self._headers(),
                json=push_payload,
                timeout=20,
            )

    def reply_text(self, reply_token: str, text: str) -> None:
        """回覆單純文字訊息（附帶底部快捷按鈕）"""
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text,
                    "quickReply": self.build_quick_reply(),
                }
            ],
        }
        requests.post(
            LINE_REPLY_ENDPOINT,
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
