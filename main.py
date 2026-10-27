import argparse
import sys

# 確保 Windows 終端機能正常印出 Emoji 與 UTF-8 字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import SEARCH_CONFIGS, TOP_N
from line_notifier import LineNotifier
from shopee_api import ShopeeAffiliateClient, get_mock_products


def run(
    dry_run: bool = False,
    test_mock: bool = False,
    custom_limit: int = None,
    custom_keyword: str = None,
) -> None:
    print("==========================================")
    print("🚀 啟動蝦皮每日熱銷排行榜 LINE 機器人")
    print("==========================================")

    shopee_client = ShopeeAffiliateClient()
    line_notifier = LineNotifier()
    limit = min(max(custom_limit if custom_limit is not None else TOP_N, 1), 50)

    if custom_keyword is not None:
        kw = custom_keyword.strip()
        title = f"🔥 蝦皮【{kw}】熱銷排行榜" if kw else "🔥 蝦皮全站熱銷排行榜"
        configs = [{"title": title, "keyword": kw, "list_type": 0, "sort_type": 2}]
    else:
        configs = SEARCH_CONFIGS

    for cfg in configs:
        title = cfg.get("title", "🔥 蝦皮熱銷排行榜")
        keyword = cfg.get("keyword", "")
        list_type = cfg.get("list_type", 0)
        sort_type = cfg.get("sort_type", 2)

        print(f"\n🔍 正在取得【{title}】(關鍵字: '{keyword or '全站'}', Top {limit})...")

        if test_mock:
            print("🧪 [測試模式] 使用內建模擬熱銷商品資料...")
            products = get_mock_products(limit=min(limit, 3))
        else:
            products = shopee_client.fetch_top_products(
                keyword=keyword,
                list_type=list_type,
                sort_type=sort_type,
                limit=limit,
            )

        if not products:
            print(f"⚠️ 【{title}】查無商品資料。")
            continue

        # 在終端機印出摘要預覽
        text_preview = line_notifier.build_text_summary(title, products)["text"]
        print("\n--- 排行榜預覽 ---")
        print(text_preview)
        print("------------------\n")

        if dry_run:
            print("🛑 [--dry-run 模式] 僅預覽結果，略過發送 LINE 推播。")
        else:
            line_notifier.send_ranking_report(title, products)

    print("\n🎉 所有排行榜任務執行完畢！")


def main() -> None:
    parser = argparse.ArgumentParser(description="蝦皮熱銷商品排行榜每日 LINE 推播機器人")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只抓取資料並在終端機顯示預覽，不發送 LINE 訊息",
    )
    parser.add_argument(
        "--test-mock",
        action="store_true",
        help="使用模擬商品資料測試（可用來單獨測試 LINE 推播卡片版面）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="指定抓取商品數量（1 ~ 50，例如 --limit 50）",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="指定搜尋關鍵字（例如 --keyword 藍牙耳機）",
    )
    args = parser.parse_args()

    try:
        run(
            dry_run=args.dry_run,
            test_mock=args.test_mock,
            custom_limit=args.limit,
            custom_keyword=args.keyword,
        )
    except Exception as exc:
        print(f"\n❌ 執行發生錯誤：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
