import os, json, requests, subprocess, urllib.parse, time, random
from gtts import gTTS
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── CONFIG ──────────────────────────────────────────
GEMINI_KEY  = os.environ["GEMINI_KEY"]
PEXELS_KEY  = os.environ["PEXELS_KEY"]
YT_TOKEN    = json.loads(os.environ["YOUTUBE_TOKEN"])
VIDEO_COUNT = int(os.environ.get("VIDEO_COUNT", "6"))

HIGH_CPM_NICHES = [
    "personal finance and investing",
    "artificial intelligence and future technology",
    "health longevity and biohacking",
    "business and entrepreneurship",
    "crypto and digital assets",
    "self improvement and productivity",
    "real estate and passive income",
    "science and space exploration"
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
    full_prompt = f"cinematic futuristic sci-fi {prompt}, dramatic lighting, ultra detailed, 8k, neon accents, dark atmosphere, no text, no watermark"
    encoded = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true&enhance=true"
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
    if effect == "zoom":
        vf = (f"zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={duration*25}:s=1280x720:fps=25")
    elif effect == "pan_right":
        vf = (f"zoompan=z='1.3':x='if(gte(x,iw*0.3),iw*0.3,x+1)':y='ih/2-(ih/zoom/2)'"
              f":d={duration*25}:s=1280x720:fps=25")
    else:
        vf = (f"zoompan=z='1.3':x='if(lte(x,0),0,x-1)':y='ih/2-(ih/zoom/2)'"
              f":d={duration*25}:s=1280x720:fps=25")
    subprocess.run([
        "ffmpeg", "-loop", "1", "-i", img_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-t", str(duration), "-pix_fmt", "yuv420p",
        out_path, "-y"
    ], check=True, capture_output=True)

# ── FETCH TRENDS ─────────────────────────────────────
def fetch_trends():
    trending = []

    # 1. YouTube trending
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "chart": "mostPopular",
                    "regionCode": "US", "maxResults": 20,
                    "key": GEMINI_KEY},
            timeout=10
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            yt_trends = [i["snippet"]["title"] for i in items[:10]]
            trending.extend(yt_trends)
            print(f"  ✅ YouTube trends: {len(yt_trends)} topics")
    except Exception as e:
        print(f"  ⚠️ YouTube trends failed: {e}")

    # 2. Google Trends RSS
    try:
        r = requests.get(
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            import re
            titles = re.findall(r'<title><!\[CDATA\[(.+?)\]\]></title>', r.text)
            google_trends = [t for t in titles if len(t) > 5][:15]
            trending.extend(google_trends)
            print(f"  ✅ Google trends: {len(google_trends)} topics")
    except Exception as e:
        print(f"  ⚠️ Google trends failed: {e}")

    # 3. Reddit hot posts
    for sub in ["investing", "technology", "singularity"]:
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
            print(f"  ⚠️ Reddit r/{sub} failed: {e}")

    print(f"  📊 Total signals: {len(trending)}")
    return trending[:40]

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
print(f"\n🧠 Planning {VIDEO_COUNT} videos based on trends...")
plan_prompt = f"""You are a viral YouTube channel strategist.

Today's trending topics across YouTube, Google Trends, and Reddit:
{trends_text}

High-CPM niches to choose from:
{chr(10).join(f"- {n}" for n in HIGH_CPM_NICHES)}

Generate exactly {VIDEO_COUNT} unique video ideas that:
1. Ride current trends OR connect trends to high-CPM niches
2. Have maximum click-through potential
3. Are completely different from each other
4. Target keywords with high advertiser value

Return ONLY a JSON array, no markdown, no backticks:
[
  {{
    "niche": "which high-CPM niche this targets",
    "trend_angle": "which trend it rides",
    "title": "viral title under 55 chars, curiosity gap or shocking claim",
    "thumbnail_text": "4-5 words ALL CAPS no punctuation shocking",
    "hook": "first 2 sentences of the video, extremely attention-grabbing"
  }}
]"""

plan_raw = gemini(plan_prompt).replace("```json", "").replace("```", "").strip()
video_plans = json.loads(plan_raw)
print(f"✅ Planned {len(video_plans)} videos")
for i, p in enumerate(video_plans):
    print(f"  {i+1}. [{p['niche'][:25]}] {p['title']}")

print(f"\n🎬 Starting production...")

# ── MAIN LOOP ─────────────────────────────────────────
success_count = 0
for video_num in range(1, min(VIDEO_COUNT, len(video_plans)) + 1):
    plan = video_plans[video_num - 1]
    print(f"\n{'='*54}")
    print(f"  📹 VIDEO {video_num}/{VIDEO_COUNT} — {plan['title']}")
    print(f"  💰 Niche: {plan['niche']}")
    print(f"{'='*54}")

    try:
        # ── SCRIPT ──────────────────────────────────
        print("✍️  Writing script...")
        script_prompt = f"""Write a complete YouTube video script.
Niche: {plan['niche']}
Title: {plan['title']}
Trend angle: {plan['trend_angle']}
Hook (use this to open): {plan['hook']}

Requirements:
- Exactly 1400 words
- Conversational, no headers, flowing paragraphs
- Hook grabs in first 10 seconds
- Build tension and curiosity throughout
- CTA at 60% mark and end
- Optimized for high watch time

Return ONLY raw JSON, no markdown, no backticks:
{{
  "script": "full 1400 word script here",
  "description": "150 word YouTube description with hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
  "scenes": [
    {{"prompt": "specific futuristic sci-fi scene for AI image generation", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}},
    {{"prompt": "...", "duration": 9}}
  ],
  "thumbnail_bg": "dramatic futuristic scene for thumbnail background no text no people"
}}"""

        script_raw = gemini(script_prompt).replace("```json", "").replace("```", "").strip()
        data = json.loads(script_raw)
        print(f"✅ Script: {len(data['script'].split())} words")

        # ── VOICEOVER ────────────────────────────────
        print("🎙️  Generating voiceover...")
        tts = gTTS(text=data["script"], lang="en", slow=False)
        tts.save("voice.mp3")
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", "voice.mp3"],
            capture_output=True, text=True
        )
        audio_duration = float(result.stdout.strip())
        print(f"✅ Voiceover: {audio_duration/60:.1f} min")

        # ── AI IMAGES + ANIMATE ───────────────────────
        print("🎨  Generating AI visuals...")
        scenes = data["scenes"]
        effects = ["zoom", "pan_right", "pan_left", "zoom", "pan_right", "pan_left", "zoom", "pan_right"]
        clip_files = []

        for idx, scene in enumerate(scenes):
            img_file = f"scene_{idx}.jpg"
            clip_file = f"scene_{idx}.mp4"
            print(f"  🖼️  Scene {idx+1}/8: {scene['prompt'][:50]}...")
            ok = gen_image(scene["prompt"], img_file)
            if not ok:
                subprocess.run([
                    "ffmpeg", "-f", "lavfi",
                    "-i", "color=c=0x0a0a2e:size=1280x720:rate=25",
                    "-t", str(scene.get("duration", 9)),
                    clip_file, "-y"
                ], check=True, capture_output=True)
            else:
                image_to_clip(img_file, clip_file,
                              duration=scene.get("duration", 9),
                              effect=effects[idx % len(effects)])
            clip_files.append(clip_file)
            time.sleep(2)

        # Fill remaining duration if audio is longer
        total_scene_duration = sum(s.get("duration", 9) for s in scenes)
        if audio_duration > total_scene_duration:
            extra_needed = audio_duration - total_scene_duration
            print(f"  ➕ Filling {extra_needed:.0f}s gap with extra scenes...")
            i = 0
            while extra_needed > 0:
                img_file = f"extra_{i}.jpg"
                clip_file = f"extra_{i}.mp4"
                dur = min(9, int(extra_needed) + 2)
                scene = scenes[i % len(scenes)]
                ok = gen_image(scene["prompt"] + " alternate angle", img_file)
                if ok:
                    image_to_clip(img_file, clip_file,
                                  duration=dur,
                                  effect=effects[i % len(effects)])
                    clip_files.append(clip_file)
                extra_needed -= dur
                i += 1
                time.sleep(2)

        print(f"✅ {len(clip_files)} animated scenes ready")

        # ── RENDER VIDEO ─────────────────────────────
        print("⚙️  Rendering final video...")
        with open("clips.txt", "w") as f:
            for cf in clip_files:
                f.write(f"file '{cf}'\n")

        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", "clips.txt",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-t", str(audio_duration + 1),
            "broll.mp4", "-y"
        ], check=True, capture_output=True)

        subprocess.run([
            "ffmpeg", "-i", "broll.mp4", "-i", "voice.mp3",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", "final_video.mp4", "-y"
        ], check=True, capture_output=True)
        print("✅ Video rendered")

        # ── THUMBNAIL ────────────────────────────────
        print("🖼️  Creating thumbnail...")
        gen_image(data["thumbnail_bg"], "bg.jpg", width=1280, height=720)

        thumb_text = plan["thumbnail_text"].upper()
        thumb_text = ''.join(c for c in thumb_text if c.isalnum() or c == ' ').strip()
        words = thumb_text.split()
        mid = max(1, len(words) // 2)
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        drawtext = (
            f"drawtext=text='{line1}':fontsize=94:fontcolor=#00FFFF"
            f":x=(w-text_w)/2:y=(h/2)-115"
            f":borderw=8:bordercolor=black@1.0:fontfile={font},"
            f"drawtext=text='{line2}':fontsize=94:fontcolor=#FFD700"
            f":x=(w-text_w)/2:y=(h/2)+25"
            f":borderw=8:bordercolor=black@1.0:fontfile={font}"
        )

        subprocess.run([
            "ffmpeg", "-i", "bg.jpg",
            "-vf", (f"scale=1280:720:force_original_aspect_ratio=increase,"
                    f"crop=1280:720,"
                    f"colorchannelmixer=rr=0.3:gg=0.3:bb=0.5,"
                    f"{drawtext}"),
            "-vframes", "1", "-q:v", "2", "thumbnail.jpg", "-y"
        ], check=True, capture_output=True)
        print("✅ Thumbnail ready")

        # ── UPLOAD ───────────────────────────────────
        print("📤  Uploading to YouTube...")
        body = {
            "snippet": {
                "title": plan["title"],
                "description": data["description"],
                "tags": data["tags"],
                "categoryId": "27"
            },
            "status": {"privacyStatus": "public"}
        }
        media = MediaFileUpload("final_video.mp4", mimetype="video/mp4", resumable=True)
        upload = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        ).execute()
        video_id = upload["id"]
        print(f"✅ https://youtube.com/watch?v={video_id}")

        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload("thumbnail.jpg")
            ).execute()
            print("✅ Thumbnail set!")
        except Exception as e:
            print(f"⚠️  Thumbnail skipped: {e}")

        success_count += 1
        print(f"\n🎉 VIDEO {video_num} LIVE — https://youtube.com/watch?v={video_id}")

        # Cleanup clips for next video
        for cf in clip_files:
            try: os.remove(cf)
            except: pass
        for i in range(8):
            try: os.remove(f"scene_{i}.jpg")
            except: pass
        for i in range(20):
            try: os.remove(f"extra_{i}.jpg")
            except: pass

        if video_num < VIDEO_COUNT:
            print(f"⏳ Cooling down 60s...")
            time.sleep(60)

    except Exception as e:
        print(f"\n❌ Video {video_num} failed: {e}")
        import traceback; traceback.print_exc()
        time.sleep(15)
        continue

print(f"\n{'='*54}")
print(f"✅ BATCH DONE — {success_count}/{VIDEO_COUNT} videos uploaded")
print(f"{'='*54}")
