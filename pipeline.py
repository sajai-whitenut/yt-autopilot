import os, json, requests, subprocess, urllib.parse, time, random, re
from gtts import gTTS
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── CONFIG ──────────────────────────────────────────
GEMINI_KEY  = os.environ["GEMINI_KEY"]
PEXELS_KEY  = os.environ["PEXELS_KEY"]
YT_TOKEN    = json.loads(os.environ["YOUTUBE_TOKEN"])
VIDEO_COUNT = int(os.environ.get("VIDEO_COUNT", "2"))

# Mass audience niches — high views, average viewer, India-friendly
MASS_NICHES = [
    "shocking facts most people don't know",
    "celebrity gossip and viral news India",
    "unbelievable true stories and mysteries",
    "motivational success stories rags to riches",
    "did you know amazing facts science",
    "top 10 lists countdown videos",
    "India news shocking viral moments",
    "conspiracy theories and hidden secrets",
    "bizarre world records and extreme events",
    "emotional stories that will make you cry",
    "cricket stars life and secrets India",
    "Bollywood celebrity secrets and news",
    "haunted places and horror true stories",
    "animals doing unbelievable things viral",
    "richest people secrets and lifestyle"
]

# Title formulas that get mass clicks
TITLE_FORMULAS = [
    "Top 10 {topic} That Will Shock You",
    "{number} Facts About {topic} Nobody Tells You",
    "The Dark Truth About {topic}",
    "Why {topic} Is Destroying India",
    "This {topic} Will Change How You See Everything",
    "Scientists Discovered {topic} And Nobody Noticed",
    "The Real Reason {topic} Happened",
    "I Can't Believe {topic} Is Real",
    "{topic}: The Untold Story",
    "What They Don't Want You To Know About {topic}"
]

# ── HELPERS ──────────────────────────────────────────
def gemini(prompt, retries=3):
    for i in range(retries):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"  Gemini retry {i+1}: {e}")
            time.sleep(5)
    raise Exception("Gemini failed after retries")

def gen_image(prompt, filename, width=1280, height=720):
    """Generate AI image — cinematic dramatic style for mass audience"""
    style = "cinematic dramatic ultra realistic, vivid colors, high contrast, eye catching, photorealistic, 8k quality, no text, no watermark, no logos"
    full_prompt = f"{prompt}, {style}"
    encoded = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true&enhance=true&model=flux"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=90)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(filename, "wb") as f:
                    f.write(r.content)
                return True
        except Exception as e:
            print(f"  Image retry {attempt+1}: {e}")
        time.sleep(8)
    return False

def image_to_clip(img_path, out_path, duration=8, effect="zoom"):
    """Ken Burns effect — renders at 1280x720 directly, ultrafast preset"""
    d = duration * 25  # frames
    if effect == "zoom":
        vf = (f"scale=2560:1440,"
              f"zoompan=z='min(zoom+0.001,1.3)'"
              f":x='iw/2-(iw/zoom/2)'"
              f":y='ih/2-(ih/zoom/2)'"
              f":d={d}:s=1280x720:fps=25")
    elif effect == "pan_right":
        vf = (f"scale=2560:1440,"
              f"zoompan=z='1.25'"
              f":x='min(iw*0.25\\,x+1)'"
              f":y='ih/2-(ih/zoom/2)'"
              f":d={d}:s=1280x720:fps=25")
    elif effect == "pan_left":
        vf = (f"scale=2560:1440,"
              f"zoompan=z='1.25'"
              f":x='max(0\\,x-1)'"
              f":y='ih/2-(ih/zoom/2)'"
              f":d={d}:s=1280x720:fps=25")
    else:  # zoom out
        vf = (f"scale=2560:1440,"
              f"zoompan=z='max(1.0\\,1.3-on*0.001)'"
              f":x='iw/2-(iw/zoom/2)'"
              f":y='ih/2-(ih/zoom/2)'"
              f":d={d}:s=1280x720:fps=25")

    subprocess.run([
        "ffmpeg", "-loop", "1", "-i", img_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-t", str(duration), "-pix_fmt", "yuv420p",
        "-r", "25", out_path, "-y"
    ], check=True, capture_output=True)

# ── FETCH TRENDS ─────────────────────────────────────
def fetch_trends():
    trending = []

    # 1. YouTube trending US + India
    for region in ["US", "IN"]:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet", "chart": "mostPopular",
                        "regionCode": region, "maxResults": 15,
                        "key": GEMINI_KEY},
                timeout=10
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                titles = [i["snippet"]["title"] for i in items]
                trending.extend(titles)
                print(f"  ✅ YouTube {region} trends: {len(titles)} topics")
        except Exception as e:
            print(f"  ⚠️ YouTube {region} trends failed: {e}")

    # 2. Google Trends RSS
    try:
        for geo in ["US", "IN"]:
            r = requests.get(
                f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200:
                titles = re.findall(r'<title><!\[CDATA\[(.+?)\]\]></title>', r.text)
                google_trends = [t for t in titles if len(t) > 5][:15]
                trending.extend(google_trends)
                print(f"  ✅ Google trends {geo}: {len(google_trends)} topics")
            time.sleep(1)
    except Exception as e:
        print(f"  ⚠️ Google trends failed: {e}")

    # 3. Reddit — mass audience subs
    for sub in ["india", "worldnews", "todayilearned", "interestingasfuck", "nextfuckinglevel"]:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                headers={"User-Agent": "yt-bot/1.0"},
                timeout=10
            )
            if r.status_code == 200:
                posts = r.json()["data"]["children"]
                trending.extend([p["data"]["title"] for p in posts])
            time.sleep(1)
        except Exception as e:
            print(f"  ⚠️ Reddit r/{sub}: {e}")

    print(f"  📊 Total signals: {len(trending)}")
    return trending[:50]

# ── AUTH YOUTUBE ─────────────────────────────────────
print("🔐 Authenticating YouTube...")
creds = Credentials(
    token=YT_TOKEN["token"],
    refresh_token=YT_TOKEN["refresh_token"],
    token_uri=YT_TOKEN["token_uri"],
    client_id=YT_TOKEN["client_id"],
    client_secret=YT_TOKEN["client_secret"],
    scopes=YT_TOKEN["scopes"]
)
if creds.expired or not creds.valid:
    creds.refresh(Request())
youtube = build("youtube", "v3", credentials=creds)
print("✅ YouTube ready")

# ── FETCH TRENDS ─────────────────────────────────────
print("\n🔍 Fetching trending topics...")
trends = fetch_trends()
trends_text = "\n".join(f"- {t}" for t in trends)

# ── PLAN ALL VIDEOS ───────────────────────────────────
print(f"\n🧠 Planning {VIDEO_COUNT} videos for mass audience...")
plan_prompt = f"""You are a viral YouTube strategist targeting MASS AUDIENCE viewers in India.

Target viewer profile:
- Average everyday person, not highly educated
- Loves shocking facts, gossip, mysteries, top 10 lists, emotional stories
- Watches content like: "Top 10 shocking facts", "Did you know", "The dark truth about X"
- Age 15-35, Indian, watches YouTube in Hindi/English
- Gets hooked by curiosity, shock, emotion, and entertainment

Today's trending topics:
{trends_text}

Mass audience niches to pick from:
{chr(10).join(f"- {n}" for n in MASS_NICHES)}

Title formulas that get mass clicks:
{chr(10).join(f"- {f}" for f in TITLE_FORMULAS)}

Generate exactly {VIDEO_COUNT} video ideas optimized for MAXIMUM VIEWS from average viewers.

Rules for titles:
- Use numbers when possible (Top 5, 7 Shocking, 10 Facts)
- Use emotional trigger words: Shocking, Secret, Dark Truth, Nobody Knows, Unbelievable
- Keep it simple — an 8th grader must understand it instantly
- Connect to trending topics where possible
- Under 55 characters

Return ONLY a JSON array, no markdown, no backticks:
[
  {{
    "niche": "which mass niche this targets",
    "trend_angle": "which trending topic it connects to",
    "title": "SEO optimized viral title under 55 chars",
    "search_keyword": "exact phrase people search on YouTube for this topic",
    "thumbnail_text": "3-4 words MAX ALL CAPS shocking emotional",
    "hook": "first 2 shocking sentences that make viewer unable to stop watching",
    "content_style": "shocking facts / top 10 list / true story / mystery / emotional"
  }}
]"""

plan_raw = gemini(plan_prompt).replace("```json", "").replace("```", "").strip()
video_plans = json.loads(plan_raw)
print(f"✅ Planned {len(video_plans)} videos")
for i, p in enumerate(video_plans):
    print(f"  {i+1}. {p['title']}")
    print(f"     🔍 Search keyword: {p['search_keyword']}")

print(f"\n🎬 Starting production...")

# ── MAIN LOOP ─────────────────────────────────────────
success_count = 0
for video_num in range(1, min(VIDEO_COUNT, len(video_plans)) + 1):
    plan = video_plans[video_num - 1]
    print(f"\n{'='*54}")
    print(f"  📹 VIDEO {video_num}/{VIDEO_COUNT}")
    print(f"  🎯 {plan['title']}")
    print(f"  🔍 Keyword: {plan['search_keyword']}")
    print(f"{'='*54}")

    try:
      # ── SCRIPT ──────────────────────────────────
        print("✍️  Writing script...")

        # Step A — get script + metadata separately
        script_prompt = f"""Write a YouTube video script for mass audience Indian viewers.

Title: {plan['title']}
Style: {plan['content_style']}
Hook: {plan['hook']}
Search keyword to use naturally 3-4 times: {plan['search_keyword']}

Rules:
- Start immediately with the hook, no intro
- Simple words, short sentences, 6th grade level
- Use suspense phrases: "But wait...", "Here's the shocking part...", "Nobody talks about this..."
- Exactly 1200 words
- End with subscribe CTA

Return ONLY raw JSON, no markdown, no backticks, no extra text:
{{
  "script": "full 1200 word script here",
  "description": "hook sentence. Then 100 words. #tag1 #tag2 #tag3 #tag4 #tag5",
  "tags": ["{plan['search_keyword']}", "shocking facts", "did you know", "viral india", "unbelievable", "top 10", "amazing facts", "truth", "must watch", "india"]
}}"""

        script_raw = gemini(script_prompt).replace("```json", "").replace("```", "").strip()
        # Fix common JSON issues
        script_raw = re.sub(r',\s*}', '}', script_raw)
        script_raw = re.sub(r',\s*]', ']', script_raw)
        data = json.loads(script_raw)
        print(f"✅ Script ready: {len(data['script'].split())} words")

        # Step B — get scenes separately (avoids giant JSON failures)
        scenes_prompt = f"""Generate 8 visual scene descriptions for a YouTube video about:
"{plan['title']}"

Return ONLY a JSON array, no markdown, no backticks:
[
  {{"prompt": "dramatic cinematic scene description, vivid, emotional, related to {plan['title']}", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}},
  {{"prompt": "...", "duration": 10}}
]"""

        scenes_raw = gemini(scenes_prompt).replace("```json", "").replace("```", "").strip()
        scenes_raw = re.sub(r',\s*]', ']', scenes_raw)
        scenes = json.loads(scenes_raw)

        # Thumbnail background
        thumb_prompt = f"""Give me one image prompt for a YouTube thumbnail background for: "{plan['title']}"
Return ONLY a plain sentence, no JSON, no quotes, no explanation."""
        data["thumbnail_bg"] = gemini(thumb_prompt).strip().strip('"')
        data["scenes"] = scenes
        print(f"✅ {len(scenes)} scenes planned")

        # ── RENDER VIDEO ─────────────────────────────
        print("⚙️  Rendering final HD video...")
        with open("clips.txt", "w") as f:
            for cf in clip_files:
                f.write(f"file '{cf}'\n")

        # Concat clips (already 1280x720 from image_to_clip)
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", "clips.txt",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-t", str(audio_duration + 1),
            "-pix_fmt", "yuv420p",
            "broll.mp4", "-y"
        ], check=True, capture_output=True)

        # Mix with voiceover
        subprocess.run([
            "ffmpeg", "-i", "broll.mp4", "-i", "voice.mp3",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "final_video.mp4", "-y"
        ], check=True, capture_output=True)

        # Verify output
        check = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size", "-of", "json", "final_video.mp4"],
            capture_output=True, text=True
        )
        info = json.loads(check.stdout)
        size_mb = int(info["format"]["size"]) / 1024 / 1024
        vid_dur = float(info["format"]["duration"]) / 60
        print(f"✅ Video: {vid_dur:.1f} min, {size_mb:.1f} MB, 1280x720 HD")

        # ── THUMBNAIL ────────────────────────────────
        print("🖼️  Creating clickbait thumbnail...")
        gen_image(data["thumbnail_bg"], "bg.jpg", width=1280, height=720)

        # Clean thumbnail text
        thumb_text = plan["thumbnail_text"].upper()
        thumb_text = ''.join(c for c in thumb_text if c.isalnum() or c == ' ').strip()
        words = thumb_text.split()
        mid = max(1, len(words) // 2)
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:]) if len(words) > 1 else ""
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        # Clickbait thumbnail: dark overlay, red accent, bold white/yellow text
        if line2:
            drawtext = (
                f"drawtext=text='{line1}'"
                f":fontsize=100:fontcolor=white"
                f":x=(w-text_w)/2:y=(h/2)-120"
                f":borderw=9:bordercolor=black@1.0:fontfile={font},"
                f"drawtext=text='{line2}'"
                f":fontsize=100:fontcolor=#FF3C00"
                f":x=(w-text_w)/2:y=(h/2)+20"
                f":borderw=9:bordercolor=black@1.0:fontfile={font}"
            )
        else:
            drawtext = (
                f"drawtext=text='{line1}'"
                f":fontsize=110:fontcolor=#FF3C00"
                f":x=(w-text_w)/2:y=(h-text_h)/2"
                f":borderw=9:bordercolor=black@1.0:fontfile={font}"
            )

        subprocess.run([
            "ffmpeg", "-i", "bg.jpg",
            "-vf", (
                f"scale=1280:720:force_original_aspect_ratio=increase,"
                f"crop=1280:720,"
                f"colorchannelmixer=rr=0.45:gg=0.35:bb=0.35,"
                f"{drawtext}"
            ),
            "-vframes", "1", "-q:v", "1",
            "thumbnail.jpg", "-y"
        ], check=True, capture_output=True)
        print("✅ Thumbnail ready")

        # ── UPLOAD ───────────────────────────────────
        print("📤  Uploading to YouTube...")

        # Build SEO-optimized description
        description = data["description"]

        body = {
            "snippet": {
                "title": plan["title"],
                "description": description,
                "tags": data["tags"],
                "categoryId": "22",   # People & Blogs — best for mass content
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            "final_video.mp4", mimetype="video/mp4",
            resumable=True, chunksize=5 * 1024 * 1024
        )
        upload = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        ).execute()
        video_id = upload["id"]
        print(f"✅ Uploaded! https://youtube.com/watch?v={video_id}")

        # Set thumbnail
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload("thumbnail.jpg")
            ).execute()
            print("✅ Thumbnail set!")
        except Exception as e:
            print(f"⚠️  Thumbnail skipped (verify at youtube.com/verify): {e}")

        success_count += 1
        print(f"\n🎉 VIDEO {video_num} LIVE!")
        print(f"   🔗 https://youtube.com/watch?v={video_id}")
        print(f"   🎯 Keyword: {plan['search_keyword']}")

        # ── CLEANUP ───────────────────────────────────
        for cf in clip_files:
            try: os.remove(cf)
            except: pass
        for i in range(8):
            try: os.remove(f"scene_{i}.jpg")
            except: pass
        for i in range(30):
            try: os.remove(f"extra_{i}.jpg")
            except: pass
        for f in ["voice.mp3", "broll.mp4", "bg.jpg", "clips.txt"]:
            try: os.remove(f)
            except: pass

        if video_num < VIDEO_COUNT:
            print(f"\n⏳ 60s cooldown before next video...")
            time.sleep(60)

    except Exception as e:
        print(f"\n❌ Video {video_num} failed: {e}")
        import traceback; traceback.print_exc()
        time.sleep(15)
        continue

print(f"\n{'='*54}")
print(f"✅ BATCH COMPLETE — {success_count}/{VIDEO_COUNT} uploaded")
print(f"{'='*54}")
