import os, json, requests, subprocess, urllib.parse, time
from gtts import gTTS
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── CONFIG ──────────────────────────────────────────
NICHE = os.environ["NICHE"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
PEXELS_KEY = os.environ["PEXELS_KEY"]
YT_TOKEN = json.loads(os.environ["YOUTUBE_TOKEN"])
VIDEO_COUNT = int(os.environ.get("VIDEO_COUNT", "1"))

# ── YOUTUBE AUTH (once, reused for all videos) ───────
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
print("✅ YouTube authenticated")

print(f"\n🎬 Starting batch: {VIDEO_COUNT} videos for niche: {NICHE}")

# ── MAIN LOOP ────────────────────────────────────────
for video_num in range(1, VIDEO_COUNT + 1):
    print(f"\n{'='*52}")
    print(f"  📹 VIDEO {video_num} of {VIDEO_COUNT}")
    print(f"{'='*52}")

    try:

        # ── STEP 1: GENERATE SCRIPT + METADATA ──────
        print("🧠 Generating script with Gemini...")

        prompt = f"""You are a YouTube scriptwriter for a faceless {NICHE} channel.
This is video number {video_num} in a batch — make it completely unique from any previous video.
Return ONLY raw valid JSON, no markdown, no backticks, no explanation:
{{
  "title": "catchy SEO title under 55 chars, curiosity or shock, unique angle",
  "description": "150 word YouTube description with hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],
  "script": "Full 1400 word voiceover script, conversational tone, no headers, no bullet points, flowing paragraphs only",
  "thumbnail_text": "5 words max ALL CAPS shocking or curiosity-driven no punctuation",
  "thumbnail_bg_query": "cinematic dramatic scene related to {NICHE} no people no text",
  "broll": ["visual term 1","visual term 2","visual term 3","visual term 4","visual term 5","visual term 6","visual term 7","visual term 8"]
}}"""

        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]}
        )
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        print(f"✅ Title: {data['title']}")

        # ── STEP 2: GENERATE VOICEOVER ───────────────
        print("🎙️ Generating voiceover...")
        tts = gTTS(text=data["script"], lang="en", slow=False)
        tts.save("voice.mp3")

        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", "voice.mp3"],
            capture_output=True, text=True
        )
        audio_duration = float(result.stdout.strip())
        print(f"✅ Voice saved — {audio_duration/60:.1f} min")

        # ── STEP 3: FETCH BROLL FROM PEXELS ──────────
        print("🎞️ Fetching B-roll clips...")
        clips = []
        headers = {"Authorization": PEXELS_KEY}

        for term in data["broll"]:
            for page in [1, 2]:
                r2 = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers=headers,
                    params={"query": term, "per_page": 3, "page": page,
                            "orientation": "landscape", "size": "medium"}
                )
                videos = r2.json().get("videos", [])
                for video in videos:
                    files = video["video_files"]
                    hd = next((f for f in files if f.get("quality") == "hd"
                               and f.get("width", 0) >= 1280), None)
                    sd = next((f for f in files if f.get("quality") == "sd"), None)
                    chosen = hd or sd or files[0]
                    clip_path = f"clip_{len(clips)}.mp4"
                    with open(clip_path, "wb") as cf:
                        cf.write(requests.get(chosen["link"]).content)
                    clips.append(clip_path)
                    if len(clips) >= 20:
                        break
                if len(clips) >= 20:
                    break
            time.sleep(0.3)

        if not clips:
            raise Exception("No Pexels clips downloaded — check PEXELS_KEY")

        print(f"✅ Downloaded {len(clips)} clips")

        # ── STEP 4: RENDER VIDEO ──────────────────────
        print("⚙️ Rendering video with FFmpeg...")

        with open("clips.txt", "w") as f:
            total = 0
            i = 0
            while total < audio_duration + 5:
                clip = clips[i % len(clips)]
                f.write(f"file '{clip}'\n")
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", clip],
                    capture_output=True, text=True
                )
                try:
                    total += float(res.stdout.strip())
                except:
                    total += 10
                i += 1

        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", "clips.txt",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                   "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-t", str(audio_duration + 1),
            "broll.mp4", "-y"
        ], check=True, capture_output=True)

        subprocess.run([
            "ffmpeg", "-i", "broll.mp4", "-i", "voice.mp3",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", "final_video.mp4", "-y"
        ], check=True, capture_output=True)
        print("✅ Video rendered")

        # ── STEP 5: GENERATE THUMBNAIL ────────────────
        print("🖼️ Generating thumbnail...")

        bg_r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": data["thumbnail_bg_query"],
                    "per_page": 1, "orientation": "landscape"}
        )
        photos = bg_r.json().get("photos", [])
        if photos:
            bg_data = requests.get(photos[0]["src"]["large2x"]).content
            with open("bg.jpg", "wb") as f:
                f.write(bg_data)
        else:
            subprocess.run([
                "ffmpeg", "-i", "broll.mp4", "-vframes", "1",
                "-q:v", "2", "bg.jpg", "-y"
            ], check=True, capture_output=True)

        thumb_text = data["thumbnail_text"].upper()
        thumb_text = ''.join(c for c in thumb_text if c.isalnum() or c == ' ')
        words = thumb_text.split()
        mid = max(1, len(words) // 2)
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        drawtext = (
            f"drawtext=text='{line1}':fontsize=88:fontcolor=white"
            f":x=(w-text_w)/2:y=(h/2)-110"
            f":borderw=7:bordercolor=black@0.95:fontfile={font},"
            f"drawtext=text='{line2}':fontsize=88:fontcolor=#FFD700"
            f":x=(w-text_w)/2:y=(h/2)+20"
            f":borderw=7:bordercolor=black@0.95:fontfile={font}"
        )

        subprocess.run([
            "ffmpeg", "-i", "bg.jpg",
            "-vf", f"scale=1280:720:force_original_aspect_ratio=increase,"
                   f"crop=1280:720,"
                   f"colorchannelmixer=rr=0.35:gg=0.35:bb=0.35,"
                   f"{drawtext}",
            "-vframes", "1", "-q:v", "2", "thumbnail.jpg", "-y"
        ], check=True, capture_output=True)
        print("✅ Thumbnail generated")

        # ── STEP 6: UPLOAD TO YOUTUBE ─────────────────
        print("📤 Uploading to YouTube...")

        body = {
            "snippet": {
                "title": data["title"],
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
        print(f"✅ Uploaded! https://youtube.com/watch?v={video_id}")

        # ── SET THUMBNAIL ──────────────────────────────
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload("thumbnail.jpg")
            ).execute()
            print("✅ Thumbnail set!")
        except Exception as e:
            print(f"⚠️ Thumbnail skipped: {e}")

        print(f"\n🎉 VIDEO {video_num} DONE — https://youtube.com/watch?v={video_id}")

        # ── CLEANUP CLIPS FOR NEXT VIDEO ──────────────
        for clip in clips:
            try:
                os.remove(clip)
            except:
                pass

        # Pause between videos to avoid rate limits
        if video_num < VIDEO_COUNT:
            print(f"⏳ Waiting 45 seconds before next video...")
            time.sleep(45)

    except Exception as e:
        print(f"\n❌ Video {video_num} failed: {e}")
        print("⏭️ Skipping to next video...")
        time.sleep(15)
        continue

print(f"\n{'='*52}")
print(f"✅ BATCH COMPLETE — {VIDEO_COUNT} videos processed")
print(f"{'='*52}")
