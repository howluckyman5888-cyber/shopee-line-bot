from concurrent.futures import ThreadPoolExecutor
import email.utils
import hashlib
from html import unescape
import json
import re
import time
from typing import Any, Dict, List
import urllib.parse
import requests

from config import (
    SHOPEE_AFFILIATE_ID,
    SHOPEE_APP_ID,
    SHOPEE_APP_SECRET,
    SHOPEE_GRAPHQL_ENDPOINT,
)


class ShopeeAffiliateClient:
    """
    蝦皮分潤商品排行榜客戶端
    支援雙模式：
    1. 免 API 金鑰模式（預設）：自動搜尋台灣蝦皮熱銷商品，並以推廣者編號 (Affiliate ID) 合成官方分潤連結
    2. 官方 Open API 模式：若已開通 App ID 與 Secret，自動使用 GraphQL API
    """

    def __init__(
        self,
        app_id: str = SHOPEE_APP_ID,
        app_secret: str = SHOPEE_APP_SECRET,
        affiliate_id: str = SHOPEE_AFFILIATE_ID,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.affiliate_id = affiliate_id or "16378530039"
        self.endpoint = SHOPEE_GRAPHQL_ENDPOINT

    @staticmethod
    def _get_accurate_timestamp() -> int:
        """取得標準伺服器 UTC 時間戳記"""
        try:
            resp = requests.head("https://open-api.affiliate.shopee.tw", timeout=5)
            date_hdr = resp.headers.get("Date")
            if date_hdr:
                return int(email.utils.parsedate_to_datetime(date_hdr).timestamp())
        except Exception:
            pass
        return int(time.time())

    def _build_headers(self, payload_str: str) -> Dict[str, str]:
        timestamp = self._get_accurate_timestamp()
        factor = f"{self.app_id}{timestamp}{payload_str}{self.app_secret}"
        signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

        auth_header = (
            f"SHA256 Credential={self.app_id}, "
            f"Timestamp={timestamp}, "
            f"Signature={signature}"
        )
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": auth_header,
        }

    def build_affiliate_link(self, clean_shopee_url: str, sub_id: str = "daily_bot") -> str:
        """
        根據蝦皮官方 Product Feed / 第三方短連結規範，將乾淨的蝦皮商品網址轉為專屬分潤連結：
        https://s.shopee.tw/an_redir?origin_link={encoded_url}&affiliate_id={affiliate_id}&sub_id={sub_id}
        """
        encoded_url = urllib.parse.quote(clean_shopee_url, safe="")
        return (
            f"https://s.shopee.tw/an_redir?origin_link={encoded_url}"
            f"&affiliate_id={self.affiliate_id}&sub_id={sub_id}"
        )

    def fetch_top_products(
        self,
        keyword: str = "",
        list_type: int = 0,
        sort_type: int = 2,
        limit: int = 10,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """優先嘗試 Open API（若已設定有效純數字 App ID），否則自動使用免 API 金鑰熱銷搜尋模式"""
        has_valid_open_api = (
            bool(self.app_id and self.app_secret)
            and self.app_id.isdigit()
            and len(self.app_secret) >= 16
        )

        if has_valid_open_api:
            try:
                return self._fetch_via_graphql(
                    keyword=keyword,
                    list_type=list_type,
                    sort_type=sort_type,
                    limit=limit,
                    page=page,
                )
            except Exception as exc:
                print(f"ℹ️ Open API 無法使用 ({exc})，自動切換為「免 API 金鑰分潤模式」...")

        return self._fetch_via_public_ranking(keyword=keyword, limit=limit)

    def _fetch_via_graphql(
        self,
        keyword: str = "",
        list_type: int = 0,
        sort_type: int = 2,
        limit: int = 10,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        args = [
            f"listType: {int(list_type)}",
            f"sortType: {int(sort_type)}",
            f"page: {int(page)}",
            f"limit: {int(limit)}",
        ]
        if keyword and keyword.strip():
            escaped_kw = json.dumps(keyword.strip(), ensure_ascii=False)
            args.insert(0, f"keyword: {escaped_kw}")

        query = f"""
        query {{
          productOfferV2({", ".join(args)}) {{
            nodes {{
              itemId
              productName
              productLink
              offerLink
              imageUrl
              price
              priceMin
              priceMax
              sales
              ratingStar
              shopName
              commissionRate
              commission
            }}
          }}
        }}
        """

        payload_dict = {"query": " ".join(query.split())}
        payload_str = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)
        headers = self._build_headers(payload_str)

        response = requests.post(
            self.endpoint,
            data=payload_str.encode("utf-8"),
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()

        if "errors" in result and result["errors"]:
            err_msg = json.dumps(result["errors"], ensure_ascii=False)
            raise RuntimeError(f"蝦皮 GraphQL API 回傳錯誤: {err_msg}")

        nodes = (
            result.get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        ) or []

        return [
            self._normalize_product(node, rank=idx + 1)
            for idx, node in enumerate(nodes[:limit])
        ]

    @staticmethod
    def _resolve_clean_shopee_url(rd_url: str, headers: Dict[str, str]) -> str:
        """解析轉址連結，提取乾淨的 https://shopee.tw/product/{shop_id}/{item_id} 原始商品網址"""
        try:
            r1 = requests.get(rd_url, headers=headers, allow_redirects=False, timeout=8)
            loc1 = r1.headers.get("Location", "")
            if not loc1:
                return "https://shopee.tw"

            if "s.shopee.tw" in loc1:
                r2 = requests.get(loc1, headers=headers, allow_redirects=False, timeout=8)
                loc2 = r2.headers.get("Location", "") or loc1
            else:
                loc2 = loc1

            # 匹配 /opaanlp/{shop_id}/{item_id} 或 /product/{shop_id}/{item_id} 或 -i.{shop_id}.{item_id}
            m = re.search(r"/(?:opaanlp|product)/(\d+)/(\d+)", loc2)
            if m:
                return f"https://shopee.tw/product/{m.group(1)}/{m.group(2)}"

            m2 = re.search(r"-i\.(\d+)\.(\d+)", loc2)
            if m2:
                return f"https://shopee.tw/product/{m2.group(1)}/{m2.group(2)}"

            clean = loc2.split("?")[0]
            if clean.startswith("https://shopee.tw"):
                return clean
        except Exception:
            pass
        return "https://shopee.tw"

    def _fetch_via_public_ranking(self, keyword: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """
        免 API 金鑰模式：從公開購物搜尋引擎抓取「蝦皮商城 / 蝦皮購物」熱銷排行商品，
        並自動移除第三方追蹤碼、替換為使用者專屬的蝦皮分潤連結 (Affiliate ID: 16378530039)
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }

        if keyword and keyword.strip():
            kw = keyword.strip()
            search_terms = [
                f"熱銷 {kw}",
                kw,
                f"人氣 {kw}",
                f"推薦 {kw}",
            ]
        else:
            # 全站綜合熱銷：涵蓋多個熱門品類，支援最多抓到 50 名
            search_terms = [
                "熱銷 冠軍",
                "熱銷 行動電源 快充",
                "熱銷 藍牙耳機",
                "熱銷 居家 收納",
                "熱銷 零食 伴手禮",
                "熱銷 保養 面膜",
                "熱銷 氣炸鍋 家電",
                "熱銷 衛生紙 日用品",
                "熱銷 益生菌 保健",
                "熱銷 咖啡 沖泡",
                "熱銷 滑鼠 鍵盤",
                "熱銷 吹風機 美容",
                "熱銷 寵物 貓砂",
                "熱銷 運動 水壺",
            ]

        candidates: List[Dict[str, Any]] = []
        seen_titles = set()
        shop_counts: Dict[str, int] = {}

        item_pattern = re.compile(
            r'data-price="(\d+)"[^>]*data-title="([^"]+)"[^>]*>.*?'
            r'href="(https://feebee\.com\.tw/rd/[^"]+)"[^>]*>.*?'
            r'<img[^>]*src="(https://img\.feebee\.tw/[^"]+)"[^>]*>.*?'
            r'<span[^>]*class="[^"]*shop[^"]*"[^>]*>(.*?)</div',
            re.S,
        )

        max_per_shop = 3 if (keyword and keyword.strip()) else max(1, limit // 10)

        for term in search_terms:
            if len(candidates) >= limit:
                break
            # 若單一關鍵字需要抓超過 15 筆，自動翻頁查詢
            pages_to_fetch = [1, 2, 3] if (keyword and keyword.strip() and limit > 15) else [1]
            for page_no in pages_to_fetch:
                if len(candidates) >= limit:
                    break
                encoded_q = urllib.parse.quote(term)
                url = f"https://feebee.com.tw/all/{encoded_q}/?price=99-&page={page_no}"
                try:
                    resp = requests.get(url, headers=headers, timeout=12)
                    if resp.status_code != 200:
                        continue
                except Exception:
                    continue

                for price_str, raw_title, rd_url, img_url, shop_html in item_pattern.findall(resp.text):
                    if len(candidates) >= limit:
                        break

                    shop_text = unescape(re.sub(r"<[^>]+>", "", shop_html).strip())
                    if "蝦皮" not in shop_text:
                        continue

                    if shop_counts.get(shop_text, 0) >= max_per_shop:
                        continue

                    title = unescape(raw_title).strip()
                    if title in seen_titles:
                        continue

                    try:
                        price_val = int(price_str)
                    except ValueError:
                        continue
                    if price_val < 50:
                        continue

                    seen_titles.add(title)
                    shop_counts[shop_text] = shop_counts.get(shop_text, 0) + 1
                    candidates.append(
                        {
                            "rank": len(candidates) + 1,
                            "title": title,
                            "price_val": price_val,
                            "rd_url": rd_url,
                            "img_url": img_url,
                            "shop_name": shop_text.replace("蝦皮商城 - ", "").replace("蝦皮購物 - ", ""),
                        }
                    )

        # 使用多執行緒並行解析蝦皮原始商品網址，大幅縮短抓取 10~50 筆的時間
        def _process_candidate(cand: Dict[str, Any]) -> Dict[str, Any]:
            rank = cand["rank"]
            price_val = cand["price_val"]
            clean_product_url = self._resolve_clean_shopee_url(cand["rd_url"], headers)
            offer_link = self.build_affiliate_link(clean_product_url)
            est_comm = max(1, int(round(price_val * 0.05)))
            node = {
                "itemId": str(rank),
                "productName": cand["title"],
                "productLink": clean_product_url,
                "offerLink": offer_link,
                "imageUrl": cand["img_url"],
                "price": str(price_val),
                "sales": f"熱銷 TOP {rank}",
                "ratingStar": "4.9",
                "shopName": cand["shop_name"],
                "commissionRate": "分潤連結已啟用",
                "commission": str(est_comm),
            }
            return self._normalize_product(node, rank=rank)

        with ThreadPoolExecutor(max_workers=10) as executor:
            collected = list(executor.map(_process_candidate, candidates))

        return collected

    @staticmethod
    def _normalize_product(node: Dict[str, Any], rank: int) -> Dict[str, Any]:
        """整理並格式化單一商品欄位，方便 LINE 卡片與文字訊息顯示"""
        name = (node.get("productName") or "未命名商品").strip()
        price_raw = node.get("price") or node.get("priceMin") or "0"
        try:
            price_val = float(price_raw)
            price_display = f"NT$ {int(round(price_val)):,}"
        except (ValueError, TypeError):
            price_display = f"NT$ {price_raw}"

        sales_raw = node.get("sales") or 0
        try:
            sales_int = int(sales_raw)
            if sales_int >= 10000:
                sales_display = f"{sales_int / 10000:.1f}萬+"
            else:
                sales_display = f"{sales_int:,}"
        except (ValueError, TypeError):
            sales_display = str(sales_raw)

        comm_rate_raw = node.get("commissionRate") or "0"
        try:
            rate_val = float(comm_rate_raw)
            if rate_val <= 1.0:
                rate_val *= 100
            formatted_num = f"{rate_val:.2f}".rstrip("0").rstrip(".")
            comm_rate_display = f"{formatted_num}%"
        except (ValueError, TypeError):
            comm_rate_display = str(comm_rate_raw)

        comm_raw = node.get("commission") or "0"
        try:
            comm_val = float(comm_raw)
            comm_display = f"NT$ {int(round(comm_val)):,}"
        except (ValueError, TypeError):
            comm_display = f"NT$ {comm_raw}"

        rating_raw = node.get("ratingStar")
        try:
            rating_display = f"{float(rating_raw):.1f}" if rating_raw else "4.9"
        except (ValueError, TypeError):
            rating_display = str(rating_raw or "4.9")

        image_url = node.get("imageUrl") or "https://cf.shopee.tw/file/tw-11134207-7r98o-lm0x4x4x4x4x4x"
        if image_url.startswith("http://"):
            image_url = "https://" + image_url[len("http://"):]

        offer_link = node.get("offerLink") or node.get("productLink") or "https://shopee.tw"
        product_link = node.get("productLink") or offer_link

        return {
            "rank": rank,
            "item_id": node.get("itemId"),
            "name": name,
            "price_display": price_display,
            "sales_display": sales_display,
            "rating_display": rating_display,
            "shop_name": (node.get("shopName") or "蝦皮精選賣場").strip(),
            "commission_rate_display": comm_rate_display,
            "commission_display": comm_display,
            "image_url": image_url,
            "offer_link": offer_link,
            "product_link": product_link,
        }


def get_mock_products(limit: int = 5) -> List[Dict[str, Any]]:
    """產生測試用的模擬熱銷商品資料（供 --test-mock 測試 LINE 推播版面使用）"""
    client = ShopeeAffiliateClient()
    samples = [
        {
            "itemId": "100001",
            "productName": "【台灣現貨】超靜音無葉掛脖風扇 隨身冷風扇 USB充電 戶外降溫神器",
            "price": "399",
            "sales": 25800,
            "ratingStar": "4.9",
            "shopName": "極致生活3C旗艦館",
            "commissionRate": "0.085",
            "commission": "34",
            "imageUrl": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80",
            "offerLink": client.build_affiliate_link("https://shopee.tw"),
            "productLink": "https://shopee.tw",
        },
        {
            "itemId": "100002",
            "productName": "【買一送一】日本熱銷大容量防水摺疊收納箱 衣服玩具整理箱 附滑輪",
            "price": "269",
            "sales": 18400,
            "ratingStar": "4.9",
            "shopName": "日系居家美學館",
            "commissionRate": "0.10",
            "commission": "27",
            "imageUrl": "https://images.unsplash.com/photo-1584100936595-c0654b55a2e2?w=600&auto=format&fit=crop&q=80",
            "offerLink": client.build_affiliate_link("https://shopee.tw"),
            "productLink": "https://shopee.tw",
        },
        {
            "itemId": "100003",
            "productName": "PD 65W 氮化鎵 GaN 三孔快充頭 支援筆電/iPhone/Type-C 折疊插角",
            "price": "590",
            "sales": 14200,
            "ratingStar": "5.0",
            "shopName": "閃電數位官方店",
            "commissionRate": "0.07",
            "commission": "41",
            "imageUrl": "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?w=600&auto=format&fit=crop&q=80",
            "offerLink": client.build_affiliate_link("https://shopee.tw"),
            "productLink": "https://shopee.tw",
        },
    ]
    return [
        ShopeeAffiliateClient._normalize_product(node, rank=idx + 1)
        for idx, node in enumerate(samples[:limit])
    ]
