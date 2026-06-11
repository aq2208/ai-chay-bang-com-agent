"""
Bronze round-trip test (no network, no LLM):
  write SocialPost bronze → connectors.threads.fetch() → normalized items → base64 image parsing.

Run: .venv/bin/python test_bronze.py
"""

from crawlers import bronze
import connectors.threads as th
from processors.image_analyzer import _to_image_input

recs = [
    {"post_hash_id": "abc123", "platform": "Threads", "matched_keyword": "zalopay", "author": "user_a",
     "content": "Nạp tiền Visa lỗi E5001 hoài, không nạp được", "posted_at": "2026-06-11 08:00:00",
     "crawled_at": "2026-06-11 09:00:00", "images_base64": ["data:image/jpeg;base64,/9j/FAKE=="]},
    {"post_hash_id": "def456", "platform": "Threads", "matched_keyword": "zalo pay", "author": "user_b",
     "content": "Quét QR ở Circle K không thanh toán được", "posted_at": "Unknown",
     "crawled_at": "2026-06-11 09:00:00", "images_base64": []},
]

p = bronze.save(recs, source="threads")
print("bronze written:", p.name, "| loaded:", len(bronze.load_latest("threads")))

items = th.fetch()
for it in items:
    print(f"  {it['id']} {it['source']} ts={it['timestamp']!r} imgs={len(it['images'])} "
          f"kw={it['matched_keyword']!r} | {it['text'][:40]}")

assert items[0]["id"] == "abc123" and items[0]["source"] == "threads"
assert items[1]["timestamp"] == "2026-06-11 09:00:00", "Unknown posted_at should fall back to crawled_at"

print("data-URI image →", {k: (v[:10] + ".." if k == "data" else v)
                           for k, v in _to_image_input("data:image/png;base64,AAAA").items()})
print("http URL image →", _to_image_input("https://x.com/a.jpg"))

p.unlink()
print("[cleanup] removed test bronze — ALL CHECKS PASSED")
