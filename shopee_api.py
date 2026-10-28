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

    @staticmethod
    def shorten_url(long_url: str) -> str:
        """將長長的分潤網址自動縮短為簡潔短網址 (is.gd / v.gd)，若失敗則回傳原網址"""
        encoded = urllib.parse.quote(long_url, safe="")
        for api_prefix in (
            "https://is.gd/create.php?format=simple&url=",
            "https://v.gd/create.php?format=simple&url=",
        ):
            try:
                resp = requests.get(f"{api_prefix}{encoded}", timeout=5)
                short = resp.text.strip()
                if resp.status_code == 200 and short.startswith("https://"):
                    return short
            except Exception:
                continue
        return long_url

    def build_affiliate_link(
        self, clean_shopee_url: str, sub_id: str = "daily_bot", shorten: bool = True
    ) -> str:
        """
        根據蝦皮官方 Product Feed / 第三方短連結規範，將乾淨的蝦皮商品網址轉為專屬分潤連結，
        並自動縮成簡潔短網址（如 https://tinyurl.com/xxxxx）
        """
        encoded_url = urllib.parse.quote(clean_shopee_url, safe="")
        long_aff_url = (
            f"https://s.shopee.tw/an_redir?origin_link={encoded_url}"
            f"&affiliate_id={self.affiliate_id}&sub_id={sub_id}"
        )
        return self.shorten_url(long_aff_url) if shorten else long_aff_url

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
                print(f"ℹ️ Open API 無法使用 ({exc})，自動切換為「蝦皮分潤後台熱銷模式」...")

        # 優先使用蝦皮分潤後台「商品推廣 - 熱銷商品」官方 API（含真實幾十萬銷量與真實分潤率）
        if not (keyword and keyword.strip()):
            try:
                official_items = self._fetch_via_affiliate_web_api(limit=limit)
                if official_items:
                    return official_items
            except Exception as exc:
                print(f"ℹ️ 分潤後台直連逾時 ({exc})，切換為商城搜尋模式...")

        return self._fetch_via_public_ranking(keyword=keyword, limit=limit)

    def _fetch_via_affiliate_web_api(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        直接從蝦皮分潤後台「商品推廣 -> 熱銷商品 (list_type=2)」撈取真實破萬銷量與真實分潤率商品
        """
        url = (
            "https://affiliate.shopee.tw/api/v3/offer/product/list"
            "?list_type=2&sort_type=1&page_offset=0&page_limit=20&client_type=1"
        )
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "af-ac-enc-dat": "6a031d8daa0096e4",
            "af-ac-enc-sz-token": "48xKaKgbhBzuCRsTsHVmmg==|uGeYnjb//o6mwdDyRL8IXU9M9AlF3urjn0eNk+Zva7DZ9WiKMZLHVZVf/UdNhcfkxsm0Ko0THXE=|6kiug8WpWDzX4Ms9|08|3",
            "affiliate-program-type": "1",
            "cookie": "_fbp=fb.1.1766652145719.198387003260954099; REC_T_ID=a6012748-e16d-11f0-a26e-9619fe650194; SPC_F=4uApGQ7a6YUBc8m5b6dHfa8emiPcBrLx; SPC_CLIENTID=NHVBcEdRN2E2WVVCngzzpsklgxekmbqd; SC_DFP=tylFZhilqigEhLihGjNaXrNYLpPdeMhV; _ga=GA1.1.1641669957.1766652150; SPC_EC=-; _gcl_gs=2.1.k1$i1788965803$u59024879; _gcl_aw=GCL.1788969108.Cj0KCQjwh4TVBhCWARIsAG0czmoKTbB5MoJ3UKZOsCFlL2wDtGE-WsyNIwsWvsvxadqPkp_zU_6qQ0AaAgDIEALw_wcB; _gcl_au=1.1.114454564.1790045639; _clck=1i5mwy9%5E2%5Egah%5E0%5E2485; SPC_ST=+J1qXfkFIYbaK1UtwT4GbgraA5+a7G5IpRmVujdoxtM6YYBEMScnwx4TBS1zRtsBi2KjCWntCwbjBAksEhQz1bkh52dh9MYYRljBVMa6nJJtBa/JjKOsHYgLwkIbm4RVt8g9vCVf7ED0lFZdIFXgAKwVYc60KtgQaABDdi7guI3K7JX0pFDlxaMO2qeqjICYHzBiu3nz8Gc8Y1S0L0tpVg==.AB/CRUKkB+B4T3x5B01JWPv2SG6agBLsQvgF3ZDtGI3M; SPC_U=40257853; SPC_R_T_ID=YnvVQhjow9ckMmnhu0mUtXEoJN96jfWnqWsaeyiMZF4kenZcz/Ry7+8+dDcTbp9GH6TyOarICcuqsQbHlXf+hscFeYQzct92hnLeqYSzQzpVcG4ByjmJQ46RvJhER8EMFY5TfwnX3vDugtckVt9SvFeGQlMpwpFgE9iAma5z5g8=; SPC_R_T_IV=UG9vdkVXQ0ZGMkFoaGJpag==; SPC_T_ID=YnvVQhjow9ckMmnhu0mUtXEoJN96jfWnqWsaeyiMZF4kenZcz/Ry7+8+dDcTbp9GH6TyOarICcuqsQbHlXf+hscFeYQzct92hnLeqYSzQzpVcG4ByjmJQ46RvJhER8EMFY5TfwnX3vDugtckVt9SvFeGQlMpwpFgE9iAma5z5g8=; SPC_T_IV=UG9vdkVXQ0ZGMkFoaGJpag==; _ga_NC4KT3JL2V=GS2.1.s1792590614$o1$g0$t1792590707$j60$l0$h0; SPC_SC_SESSION=gZhPtdYSMPSF9YYsBtcjdQNz592P1SqiOUSntiCSDJ1jlGV5wwY4EEsIS5OBfKHZ7yAmOdFO3SLHXRe3N/OORIPEoa8rmN2wvbKbkBuuWqkSmUOPAkIIkDTvzPqZqUP9gCFS+2Uy4TVK+jMxmMGmXdMwFfcG6SHynTKck1ZPCSHEfLPUMdECB6PpOSygO4MFL+xixIMLQ/WpVf1TBhomKD5N6gyjrGdr1wJyio05OAzX1p3vuh3yyv8CV97hSesOzPLVeVLamk9HMXIFMyUGedw==_1_40257853; SPC_SC_MAIN_SHOP_SA_UD=0; SPC_STK=G2RkVL4C7V7Thp4GqUlkjnRELsvDAH4fvL7r4NsJF2j87kUlAVSu8vK3cjvHSOLJLXBA216ZjgJYuUsN5DetoPv6KSWX8sRn+rJwOEbv2jE6+1l3UFld2k78eA42aWMA86CpX047pf264jz5kdy5JyVa0gYW8NDFPe2FuwJ4EJE+D1s4RWsaqToJtIZLAT0MRJK2G4+gD3agfIxlf2nY9v/N7dFNUPt8OEkCUCYoChAr78IsCcM/4TYAMbTRRRAhoRF5QihHIyk6kthyEMx2670wK4WNdf3nJShP5rCms/ObUkU+IvblPRVzf2ubFXZs4fAG9vQQQ1N2omswcP792dWg+5Z9CNT2D6NNwtszm7tu5ApCazNo25NKr1pTS4I87lZc6/G+qWYlarnMNG/bfeGdsaRtsmB71fqp5Mf9ptNckqo9ObNFQBK86kgC4BQoIwRW8FOrk4BibZqiC9ImO06mnDKe9o3veXLWOdHNjoHBD+0O+XdeVYpl5lnT0aoT; CTOKEN=kAWP6c1qEfG4yD7F%2BRDgWg%3D%3D; _med=refer; _QPWSDCXHZQA=dea252ad-0924-4a7b-a7c0-01e2c4ff10f6; REC7iLP4Q=9c02f519-2c5e-424e-98a4-9efe009198f2; _med=affiliates; csrftoken=69X641ZTE8npwbwA6O99rhJZVaPh0k0h; SPC_SI=la/EagAAAAB1bEZxRnhlVGHz6QIAAAAAZjJ3U1NkT3I=; SPC_CDS_CHAT=30a1354c-db5d-4fe9-bde7-f215fa21be04; _sapid=36f9c7ad5a4e1ec733a40baf15ab77478347855eb1660f0c3973b770; language=zh-Hant; language=zh-Hant; 40257853_hasShowedPaymentFillingTip=1; shopee_webUnique_ccd=7xU48Y3BbEmrE7s4iTuUbw%3D%3D%7Cye1J%2B%2FMUEMlOtH4%2Btjkwl3dxpj%2FvFUWfM3pCuY9f6FXK5gjGwJx1%2FpV5KGNNa1C739A5SQjkTp8%3D%7C412orwVD8hb9KcUP%7C08%7C3; ds=87fd70d85d72c3b3a915c2a5ac35182b; sense_sa_r=s; _ga_E4FV1WFT0L=GS2.1.s1793164617$o4$g1$t1793164631$j46$l0$h0; _ga_E1H7XE0312=GS2.1.s1793170942$o393$g0$t1793170942$j60$l0$h745541347",
            "referer": "https://affiliate.shopee.tw/offer/product_offer",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
            "x-sap-ri": "d0a1e16aad70a802f853b533050118a457b32ce214b208be5b04",
            "x-sap-sec": "SF9fP8Yy1+Y39cSFX+aFXcTFH+b0XKyFA9aLX01FJ+xPXByFZ+bMX2aFY+xIX00FD9aZXQaFP+b1X0SFh+aJXRkFxibVXcTFm+aRXdyFy+b+XMdF89atXdSFgkxiXN1FI+ahXM+FC+aMXcqFPiaeX09F4ixFXB1Fz+bdXK4F9+b8XQdFO9bNX+aF2+yFX+aFX+wmYRKQX+aF7+yQ0TZPXiaFX+aFumNmch2UXiaFj+iFX30z5goFX2ecf+yFX+aFDIdFX0a0X+ZQDy1AX+aFlurzY+aFX67AX+aJX9aFBOgFOiaFXRbUXkaFv+iFX+aFvIG755DrX+aFBdgyyx9PXkaFX+ZjugaDX+bZmiawbyHgWAYsX78hXiaFX+ZAdN1TX+ZUXkaFXL5qvvZztJrmtsrOX+xVDv7FX+Zl1y0rnKOT6KIgK7uY45LyDVJLZd9TSaq1Ln8iPQbEI0lf2FhGQ/CqlfuPV2L79XiKiEMu/oUVIFe53PYfi3trB+vBkn5x4eFVoc5AFEy5WYOV46WHpzfsSbWk2ELKwMvlz5PEG5lRMM4DNH2NDDN93vvGhkp6dLQzAh0YsLh/f4hWXoDJKihhh//TWDz3pmLcF5LAtVkouf0m0xjKa20b5FCisf0wSkEIRpi5UfcbROPJG+EMn16aXsoHNQCirWEaJX68su9XSgb9roLi5zABFoYNPFo0jHPVP4gUUSXlLGKE1on9RRFc8+aFXcMwNSJjdVDW9+aFXdg93lOpX+aFVSAI+6JG6F6LUH8PNJbfvKR+tKgVFZ9lbstfVKvJQ3DdabXWvheqjBEXvw8ZjMOEg1MgS/jeNDbgXIJv6WkgJTL69T38sDQGcEjzCmH1EEAl++dTtADMUCyaqOEwZHluRsIusFK1tWBsUCmtE9RDQ6w7HFWpGMx7lSkH5vYjFxkv9G0ty7rytTlVd6QiZBL5IvRp7wFj+bvnP56G3Pr6GLcGxfrzEsXEIRl7fA6NX+a8X+aFyrbB5+oFX+ZJVK+mCohqEETosi5sX+aFX+aFX+aFX+buX+aF5dPZbjBYMSn9g6N+DugD+oXUcF9YItZ2HQtszJIvRhMQtsrXCYPlevwWckA+Int5pDULglh7RLcQavHIGvZlhnwRN++DO1sS4PmaWDOjX+aFX+aFX+aFXNiFX+xcYU2iVbDF/t1oKRTQBqUp/FteXB1FX+Z4VCdtv0O8LZH4hzS75bn/S8lR9lKXknDRUe4qCbLxLxTQ3AdFX+aFU+aFX/y+3k9KP0Zo0QxSmDPbrGe5VZ4VCbsFKEaM/zHEP6nLLPlS8IDVd/IdVK0UCbLlL/y3h+oLP6D7X+aFX+7FX+ZSTUO0/tJIP9aFX+aFX+aFu+aFXRcRImXTTNraZTUWCOyU7ahZVgkspoPqdHHPQtTOvMDI8+aFX6YDI85wEvC18+aFXMz51l1MUM0+X+aFXK==",
            "x-sz-sdk-version": "1.12.21",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        js = resp.json()
        raw_list = js.get("data", {}).get("list", []) or []
        if not raw_list:
            return []

        def _convert_official_item(idx_and_item: Any) -> Dict[str, Any]:
            idx, it = idx_and_item
            rank = idx + 1
            card = it.get("batch_item_for_item_card_full", {})
            price_val = int(card.get("price", 0)) // 100000
            sold = int(card.get("historical_sold") or card.get("global_sold") or 0)
            comm_rate_str = (
                it.get("default_commission_rate")
                or it.get("seller_commission_rate")
                or "5%"
            )
            try:
                rate_num = float(comm_rate_str.replace("%", "").strip()) / 100.0
            except ValueError:
                rate_num = 0.05
            est_comm = max(1, int(round(price_val * rate_num)))

            product_link = (
                it.get("product_link")
                or f"https://shopee.tw/product/{card.get('shopid')}/{card.get('itemid')}"
            )
            offer_link = self.build_affiliate_link(product_link)
            img_hash = card.get("image", "")
            image_url = (
                f"https://cf.shopee.tw/file/{img_hash}"
                if img_hash and not img_hash.startswith("http")
                else img_hash
            )
            rating_val = card.get("item_rating", {}).get("rating_star", 4.9)

            node = {
                "itemId": str(it.get("item_id") or card.get("itemid") or rank),
                "productName": card.get("name", "蝦皮熱銷商品"),
                "productLink": product_link,
                "offerLink": offer_link,
                "imageUrl": image_url,
                "price": str(price_val),
                "sales": sold,
                "ratingStar": f"{float(rating_val):.1f}",
                "shopName": card.get("shop_name") or "蝦皮官方熱銷賣場",
                "commissionRate": comm_rate_str,
                "commission": str(est_comm),
            }
            return self._normalize_product(node, rank=rank)

        selected = list(enumerate(raw_list[:limit]))
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(_convert_official_item, selected))

        # 若使用者要求超過 20 筆 (例如 30~50 筆)，不足的部分自動由商城熱門商品補齊
        if len(results) < limit:
            extra = self._fetch_via_public_ranking(keyword="", limit=limit - len(results))
            for item in extra:
                item["rank"] = len(results) + 1
                results.append(item)

        return results

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
            # 自動修正台灣常見同音字，並針對過於廣泛的單詞補強品類詞
            kw = keyword.strip().replace("藍芽", "藍牙")
            if kw == "居家":
                kw = "居家 收納 日用"
            elif kw == "3C" or kw == "3c":
                kw = "快充 行動電源 藍牙耳機"
            elif kw in {"美妝", "保養"}:
                kw = "保濕 面膜 精華液"
            search_terms = [
                kw,
                f"{kw} 旗艦",
            ]
            max_per_term = limit
        else:
            # 全站綜合熱銷：鎖定各大品類知名規格詞，優先抓取蝦皮商城官方店商品
            search_terms = [
                "行動電源 自帶線 快充",
                "真無線 藍牙耳機 降噪",
                "收納箱 整理箱 摺疊",
                "堅果 零食 禮盒",
                "保濕 面膜 精華液",
                "氣炸鍋 烤箱",
                "抽取式 衛生紙 箱購",
                "益生菌 葉黃素",
                "濾掛 咖啡 禮盒",
                "無線滑鼠 機械鍵盤",
                "負離子 吹風機",
                "豆腐貓砂 寵物",
                "316 保溫杯 隨行杯",
            ]
            # 每個分類平均抽取，確保排行榜多元豐富
            max_per_term = max(2, (limit + 4) // 5)

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
            term_count = 0
            # 若單一關鍵字需要抓超過 15 筆，自動翻頁查詢
            pages_to_fetch = [1, 2, 3] if (keyword and keyword.strip() and limit > 15) else [1]
            for page_no in pages_to_fetch:
                if len(candidates) >= limit or term_count >= max_per_term:
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
                    if len(candidates) >= limit or term_count >= max_per_term:
                        break

                    shop_text = unescape(re.sub(r"<[^>]+>", "", shop_html).strip())
                    # 嚴格只挑選「蝦皮商城」官方品牌旗艦店，全面封殺「蝦皮購物精選」（比價網付費置頂廣告，常為0銷量小賣家）
                    if "蝦皮商城" not in shop_text:
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
                    term_count += 1
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
