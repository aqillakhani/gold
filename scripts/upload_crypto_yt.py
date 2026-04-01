"""One-off upload of content_11 to CryptoFlow YouTube channel."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold.config import Config
from gold.platforms.youtube import YouTubeAdapter


async def main():
    config = Config()
    yt = YouTubeAdapter(config, account_id="crypto_finance")

    video_path = Path(r"C:\Users\claws\OneDrive\Desktop\gold\data\media\rendered\content_11_master_20260313_134606.mp4")
    caption = "This $0.03 Altcoin Could Hit $1 Before Bitcoin Reaches $100K"
    hashtags = [
        "#crypto", "#bitcoin", "#altcoin", "#trading",
        "#finance", "#defi", "#blockchain", "#investment",
        "#btc", "#cryptocurrency",
    ]
    thumbnail = Path(r"C:\Users\claws\OneDrive\Desktop\gold\data\media\images\content_11_thumb_20260313_033502.png")

    print(f"Uploading {video_path.name} to CryptoFlow YouTube...")
    result = await yt.post(video_path, caption, hashtags, thumbnail_path=thumbnail)
    print(f"Done! Video ID: {result['post_id']}")
    print(f"URL: https://youtube.com/shorts/{result['post_id']}")


if __name__ == "__main__":
    asyncio.run(main())
