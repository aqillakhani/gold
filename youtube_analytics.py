#!/usr/bin/env python3
"""YouTube Analytics Analysis for Gold Platform Channels."""

import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import sqlite3

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Configuration
CHANNELS = {
    "reddit_stories": {
        "display_name": "StoryVault",
        "channel_id": "UCAMQuZQXguQjWdus-EZTb-g",
        "client_id_env": "YOUTUBE_CLIENT_ID_REDDIT",
        "client_secret_env": "YOUTUBE_CLIENT_SECRET_REDDIT",
        "refresh_token_env": "YOUTUBE_REFRESH_TOKEN_REDDIT",
    },
    "crypto_finance": {
        "display_name": "CryptoFlow",
        "channel_id": "UCdY8-HGr3KAU8BRK3IjA9jg",
        "client_id_env": "YOUTUBE_CLIENT_ID_CRYPTO",
        "client_secret_env": "YOUTUBE_CLIENT_SECRET_CRYPTO",
        "refresh_token_env": "YOUTUBE_REFRESH_TOKEN_CRYPTO",
    },
    "ai_tools": {
        "display_name": "ToolStack",
        "channel_id": "UCQiULF-Qp7TgVQFLWyM929Q",
        "client_id_env": "YOUTUBE_CLIENT_ID_TECH",
        "client_secret_env": "YOUTUBE_CLIENT_SECRET_TECH",
        "refresh_token_env": "YOUTUBE_REFRESH_TOKEN_TECH",
    },
    "true_crime": {
        "display_name": "Cold Cases",
        "channel_id": "UCgqyZTmFSuqast1BJuQlSjg",
        "client_id_env": "YOUTUBE_CLIENT_ID_TRUECRIME",
        "client_secret_env": "YOUTUBE_CLIENT_SECRET_TRUECRIME",
        "refresh_token_env": "YOUTUBE_REFRESH_TOKEN_TRUECRIME",
    },
}


def load_env():
    """Load environment from secrets/.env"""
    env = {}
    env_path = Path(__file__).parent / "secrets" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    return env


def get_youtube_service(env: dict, channel_key: str) -> tuple[object, str]:
    """Get authenticated YouTube service for a channel."""
    config = CHANNELS[channel_key]

    client_id = env.get(config["client_id_env"])
    client_secret = env.get(config["client_secret_env"])
    refresh_token = env.get(config["refresh_token_env"])

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(f"Missing credentials for {channel_key}")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    creds.refresh(Request())

    youtube = build("youtube", "v3", credentials=creds)
    return youtube, config["channel_id"]


def get_channel_info(youtube: object, channel_id: str) -> dict:
    """Get basic channel info including subscriber count."""
    request = youtube.channels().list(
        part="statistics,snippet",
        id=channel_id,
    )
    response = request.execute()

    if not response.get("items"):
        return {}

    item = response["items"][0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    return {
        "channel_id": channel_id,
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "published_at": snippet.get("publishedAt"),
    }


def get_all_videos(youtube: object, channel_id: str) -> list[dict]:
    """Fetch all videos from a channel."""
    videos = []

    # First, get the uploads playlist ID
    request = youtube.channels().list(
        part="contentDetails",
        id=channel_id,
    )
    response = request.execute()

    if not response.get("items"):
        return videos

    uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Now fetch all videos from the uploads playlist
    request = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=50,
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            video_id = item["contentDetails"]["videoId"]
            title = item["snippet"]["title"]
            published_at = item["snippet"]["publishedAt"]
            videos.append({
                "video_id": video_id,
                "title": title,
                "published_at": published_at,
            })

        if "nextPageToken" in response:
            request = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=response["nextPageToken"],
            )
        else:
            request = None

    return videos


def get_video_stats(youtube: object, video_ids: list[str]) -> dict:
    """Get view count, likes, comments for videos."""
    if not video_ids:
        return {}

    stats_map = {}

    # Fetch in batches of 50
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        request = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(batch),
        )
        response = request.execute()

        for item in response.get("items", []):
            vid = item["id"]
            s = item.get("statistics", {})
            snippet = item.get("snippet", {})
            stats_map[vid] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "favorites": int(s.get("favoriteCount", 0)),
                "title": snippet.get("title"),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt"),
                "duration_seconds": parse_duration(snippet.get("duration", "PT0S")),
            }

    return stats_map


def parse_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string to seconds."""
    # Simple parser for PT format
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


def calculate_engagement_metrics(videos: list[dict]) -> dict:
    """Calculate engagement metrics across videos."""
    if not videos:
        return {}

    total_views = sum(v["views"] for v in videos)
    total_likes = sum(v["likes"] for v in videos)
    total_comments = sum(v["comments"] for v in videos)

    metrics = {
        "total_videos": len(videos),
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "avg_views_per_video": total_views / len(videos) if videos else 0,
        "avg_likes_per_video": total_likes / len(videos) if videos else 0,
        "avg_comments_per_video": total_comments / len(videos) if videos else 0,
        "overall_engagement_rate": (total_likes + total_comments) / total_views if total_views > 0 else 0,
        "like_rate": total_likes / total_views if total_views > 0 else 0,
        "comment_rate": total_comments / total_views if total_views > 0 else 0,
    }

    # Top performing video
    if videos:
        top_video = max(videos, key=lambda v: v["views"])
        metrics["top_video"] = {
            "title": top_video["title"],
            "views": top_video["views"],
            "likes": top_video["likes"],
            "comments": top_video["comments"],
        }

    return metrics


def analyze_titles_and_hooks(videos: list[dict]) -> dict:
    """Analyze which titles/hooks correlate with higher views."""
    if not videos:
        return {}

    # Sort by views
    sorted_videos = sorted(videos, key=lambda v: v["views"], reverse=True)

    top_10_pct = sorted_videos[:max(1, len(sorted_videos) // 10)]
    bottom_10_pct = sorted_videos[-max(1, len(sorted_videos) // 10):]

    # Extract words from titles
    from collections import Counter

    def extract_words(texts):
        words = []
        for text in texts:
            # Simple word extraction
            import re
            w = re.findall(r'\b\w+\b', text.lower())
            words.extend(w)
        return words

    top_words = Counter(extract_words([v["title"] for v in top_10_pct]))
    bottom_words = Counter(extract_words([v["title"] for v in bottom_10_pct]))

    # Find distinctive words in top videos
    distinctive_words = {}
    for word, count in top_words.most_common(10):
        if len(word) > 3:  # Filter short words
            bottom_count = bottom_words.get(word, 0)
            if count > bottom_count:
                distinctive_words[word] = {
                    "top_freq": count,
                    "bottom_freq": bottom_count,
                }

    return {
        "top_10_videos": [
            {
                "title": v["title"],
                "views": v["views"],
                "engagement_rate": (v["likes"] + v["comments"]) / v["views"] if v["views"] > 0 else 0,
            }
            for v in top_10_pct
        ],
        "distinctive_words_in_top_content": distinctive_words,
        "avg_views_top_10": sum(v["views"] for v in top_10_pct) / len(top_10_pct) if top_10_pct else 0,
        "avg_views_bottom_10": sum(v["views"] for v in bottom_10_pct) / len(bottom_10_pct) if bottom_10_pct else 0,
    }


def calculate_view_velocity(video: dict, channel_info: dict) -> dict:
    """Calculate views per day since upload."""
    published_at = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
    now = datetime.now(published_at.tzinfo)
    days_since = (now - published_at).days

    if days_since == 0:
        days_since = 1

    return {
        "views_per_day": video["views"] / days_since,
        "days_since_upload": days_since,
    }


def calculate_subscriber_conversion(channel_info: dict, total_views: int) -> float:
    """Calculate subscriber conversion rate."""
    if total_views == 0:
        return 0
    return channel_info.get("subscribers", 0) / total_views


def compare_to_benchmarks() -> dict:
    """Provide typical benchmark data for new YouTube Shorts channels."""
    return {
        "new_channel_typical_views_per_video": "50-500 views",
        "new_channel_typical_engagement_rate": "2-8%",
        "new_channel_typical_subscriber_conversion": "0.5-2%",
        "growing_channel_views_per_video": "1000-5000 views",
        "growing_channel_engagement_rate": "3-10%",
        "growing_channel_subscriber_conversion": "1-4%",
        "established_channel_views_per_video": "10000+ views",
        "established_channel_engagement_rate": "5-15%",
        "established_channel_subscriber_conversion": "2-6%",
        "note": "Based on typical YouTube Shorts performance (2024-2025)",
    }


def main():
    """Main analysis function."""
    env = load_env()
    results = {}

    print("=" * 80)
    print("GOLD PLATFORM - YOUTUBE ANALYTICS ANALYSIS")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    for channel_key, config in CHANNELS.items():
        print(f"\nAnalyzing {config['display_name']} ({channel_key})...")
        print("-" * 80)

        try:
            # Get YouTube service
            youtube, channel_id = get_youtube_service(env, channel_key)

            # Get channel info
            channel_info = get_channel_info(youtube, channel_id)
            print(f"  Channel: {channel_info.get('title')}")
            print(f"  Subscribers: {channel_info.get('subscribers'):,}")
            print(f"  Total Views (all-time): {channel_info.get('total_views'):,}")
            print(f"  Total Videos: {channel_info.get('video_count')}")

            # Get all videos
            videos_meta = get_all_videos(youtube, channel_id)
            if not videos_meta:
                print("  No videos found")
                continue

            print(f"  Videos to analyze: {len(videos_meta)}")

            # Get statistics for all videos
            video_ids = [v["video_id"] for v in videos_meta]
            stats_map = get_video_stats(youtube, video_ids)

            # Merge metadata with stats
            videos_full = []
            for meta in videos_meta:
                vid = meta["video_id"]
                if vid in stats_map:
                    video_data = {**meta, **stats_map[vid]}
                    videos_full.append(video_data)

            # Calculate metrics
            engagement_metrics = calculate_engagement_metrics(videos_full)
            title_analysis = analyze_titles_and_hooks(videos_full)

            # Calculate view velocity for each video
            view_velocities = [
                calculate_view_velocity(v, channel_info)
                for v in videos_full[:10]  # Top 10
            ]
            avg_velocity = sum(v["views_per_day"] for v in view_velocities) / len(view_velocities) if view_velocities else 0

            # Subscriber conversion
            subscriber_conversion = calculate_subscriber_conversion(
                channel_info,
                engagement_metrics.get("total_views", 0)
            )

            # Store results
            results[channel_key] = {
                "channel_info": channel_info,
                "engagement_metrics": engagement_metrics,
                "title_analysis": title_analysis,
                "view_velocity": {
                    "avg_views_per_day": avg_velocity,
                    "analysis_based_on_videos": len(view_velocities),
                },
                "subscriber_conversion_rate": subscriber_conversion,
                "subscriber_conversion_percentage": subscriber_conversion * 100,
                "videos_analyzed": len(videos_full),
            }

            # Print summary
            print(f"\n  ENGAGEMENT METRICS:")
            print(f"    Total Views: {engagement_metrics.get('total_views'):,}")
            print(f"    Total Likes: {engagement_metrics.get('total_likes'):,}")
            print(f"    Total Comments: {engagement_metrics.get('total_comments'):,}")
            print(f"    Avg Views/Video: {engagement_metrics.get('avg_views_per_video'):,.0f}")
            print(f"    Engagement Rate: {engagement_metrics.get('overall_engagement_rate')*100:.2f}%")
            print(f"    Like Rate: {engagement_metrics.get('like_rate')*100:.2f}%")
            print(f"    Comment Rate: {engagement_metrics.get('comment_rate')*100:.3f}%")
            print(f"\n  VIEW VELOCITY:")
            print(f"    Avg Views/Day: {avg_velocity:,.1f}")
            print(f"\n  SUBSCRIBER CONVERSION:")
            print(f"    Rate: {subscriber_conversion*100:.2f}%")

            if title_analysis.get("top_10_videos"):
                print(f"\n  TOP PERFORMING VIDEO:")
                top = title_analysis["top_10_videos"][0]
                print(f"    Title: {top['title']}")
                print(f"    Views: {top['views']:,}")
                print(f"    Engagement Rate: {top['engagement_rate']*100:.2f}%")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Comparative analysis
    print("\n" + "=" * 80)
    print("COMPARATIVE ANALYSIS ACROSS NICHES")
    print("=" * 80)

    if len(results) > 1:
        print("\nEngagement Rate Rankings:")
        ranked = sorted(
            results.items(),
            key=lambda x: x[1]["engagement_metrics"].get("overall_engagement_rate", 0),
            reverse=True
        )
        for i, (key, data) in enumerate(ranked, 1):
            config = CHANNELS[key]
            rate = data["engagement_metrics"].get("overall_engagement_rate", 0) * 100
            print(f"  {i}. {config['display_name']}: {rate:.2f}%")

        print("\nAverage Views Per Video Rankings:")
        ranked = sorted(
            results.items(),
            key=lambda x: x[1]["engagement_metrics"].get("avg_views_per_video", 0),
            reverse=True
        )
        for i, (key, data) in enumerate(ranked, 1):
            config = CHANNELS[key]
            views = data["engagement_metrics"].get("avg_views_per_video", 0)
            print(f"  {i}. {config['display_name']}: {views:,.0f} views/video")

        print("\nSubscriber Conversion Rankings:")
        ranked = sorted(
            results.items(),
            key=lambda x: x[1].get("subscriber_conversion_percentage", 0),
            reverse=True
        )
        for i, (key, data) in enumerate(ranked, 1):
            config = CHANNELS[key]
            conv = data.get("subscriber_conversion_percentage", 0)
            print(f"  {i}. {config['display_name']}: {conv:.3f}%")

    # Benchmark comparison
    print("\n" + "=" * 80)
    print("BENCHMARK COMPARISON")
    print("=" * 80)
    benchmarks = compare_to_benchmarks()
    print("\nTypical YouTube Shorts Performance (2024-2025):")
    for key, value in benchmarks.items():
        if not key.startswith("note"):
            print(f"  {key}: {value}")

    print("\nYour Channel Performance vs Benchmarks:")
    for channel_key, data in results.items():
        config = CHANNELS[channel_key]
        avg_views = data["engagement_metrics"].get("avg_views_per_video", 0)
        engagement = data["engagement_metrics"].get("overall_engagement_rate", 0) * 100
        subs_conv = data.get("subscriber_conversion_percentage", 0)

        print(f"\n  {config['display_name']}:")

        # Views comparison
        if avg_views < 500:
            tier = "NEW (50-500 views)"
        elif avg_views < 5000:
            tier = "GROWING (1k-5k views)"
        else:
            tier = "ESTABLISHED (10k+ views)"
        print(f"    Views Per Video: {avg_views:,.0f} → {tier}")

        # Engagement comparison
        if engagement < 2:
            tier = "Below Average"
        elif engagement < 8:
            tier = "Average"
        elif engagement < 15:
            tier = "Above Average"
        else:
            tier = "Excellent"
        print(f"    Engagement Rate: {engagement:.2f}% → {tier}")

        # Subscriber conversion comparison
        if subs_conv < 0.5:
            tier = "Below Average"
        elif subs_conv < 2:
            tier = "Average"
        elif subs_conv < 6:
            tier = "Above Average"
        else:
            tier = "Excellent"
        print(f"    Subscriber Conversion: {subs_conv:.3f}% → {tier}")

    # Actionable insights
    print("\n" + "=" * 80)
    print("ACTIONABLE INSIGHTS")
    print("=" * 80)

    if results:
        # Find best engagement niche
        best_engagement = max(
            results.items(),
            key=lambda x: x[1]["engagement_metrics"].get("overall_engagement_rate", 0)
        )
        print(f"\n1. BEST ENGAGEMENT NICHE: {CHANNELS[best_engagement[0]]['display_name']}")
        print(f"   Engagement Rate: {best_engagement[1]['engagement_metrics'].get('overall_engagement_rate', 0)*100:.2f}%")
        print("   → RECOMMENDATION: Analyze what makes this niche engage better.")
        print("     Consider similar hooks/titles in lower-performing channels.")

        # Find highest growth potential
        best_velocity = max(
            results.items(),
            key=lambda x: x[1]["view_velocity"].get("avg_views_per_day", 0)
        )
        print(f"\n2. FASTEST GROWING: {CHANNELS[best_velocity[0]]['display_name']}")
        print(f"   Views/Day: {best_velocity[1]['view_velocity'].get('avg_views_per_day', 0):,.1f}")
        print("   → RECOMMENDATION: Double down on this content type.")
        print("     Increase posting frequency for this niche.")

        # Subscriber conversion insights
        best_conversion = max(
            results.items(),
            key=lambda x: x[1].get("subscriber_conversion_percentage", 0)
        )
        print(f"\n3. BEST SUBSCRIBER CONVERSION: {CHANNELS[best_conversion[0]]['display_name']}")
        print(f"   Rate: {best_conversion[1].get('subscriber_conversion_percentage', 0):.3f}%")
        print("   → RECOMMENDATION: Optimize CTAs and channel branding for this niche.")

        # Performance tier analysis
        print(f"\n4. GROWTH STAGE ANALYSIS:")
        for channel_key, data in results.items():
            config = CHANNELS[channel_key]
            avg_views = data["engagement_metrics"].get("avg_views_per_video", 0)

            if avg_views < 500:
                print(f"   {config['display_name']}: Early stage → Focus on consistency & virality")
            elif avg_views < 5000:
                print(f"   {config['display_name']}: Growth phase → Optimize format & posting times")
            else:
                print(f"   {config['display_name']}: Established → Monetize & scale")

    # Save detailed results
    output_file = Path(__file__).parent / "youtube_analytics_report.json"
    with open(output_file, "w") as f:
        # Convert datetime objects to strings for JSON serialization
        results_serializable = {}
        for key, data in results.items():
            results_serializable[key] = json.loads(
                json.dumps(data, default=str)
            )
        json.dump(results_serializable, f, indent=2, default=str)

    print(f"\n" + "=" * 80)
    print(f"Detailed report saved to: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
