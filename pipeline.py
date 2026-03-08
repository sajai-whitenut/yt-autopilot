import os, json, requests, subprocess, urllib.parse
from gtts import gTTS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── CONFIG ──────────────────────────────────────────
NICHE = os.environ["NICHE"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
PEXELS_KEY = os.environ["PEXELS_KEY"]
YT_TOKEN = json.loads(os.environ["YOUTUBE_TOKEN"])

# ── STEP 1: GENERATE SCRIPT + METADATA ──────────────
print("🧠 Generating script with Gemini...")

prompt = f"""You are a YouTube scriptwriter for a faceless {NICHE} channel.
Return ONLY raw valid JSON, no markdown, no backticks, no explanation:
{{
  "title": "catchy SEO title under 60 chars",
  "description": "150 word YouTube description with hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5"],
  "script": "Full 700 word voiceover script, conversational tone, no headers",
  "thumbnail_prompt": "YouTube thumbnail: bold white text saying the title, dark dramatic background, high contrast, photorealistic",
  "broll": ["search term 1","search term 2","search term 3","search term 4","search term 5"]
}}"""

r = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
    json={"contents": [{"parts": [{"text": prompt}]}]}
)
r.raise_for_status()
raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
raw = raw.strip().replace("```json","").replace("```","").strip()
data = json.loads(raw)
print(f"✅ Title: {data['title']}")

# ── STEP 2: GENERATE VOICEOVER ───────────────────────
print("🎙️ Generating voiceover with gTTS...")
tts = gTTS(text=data["script"], lang="en", slow=False)
tts.save("voice.mp3")
print("✅ voice.mp3 saved")

# ── STEP 3: FETCH BROLL FROM PEXELS ─────────────────
print("🎞️ Fetching B-roll from Pexels...")
clips = []
headers = {"Authorization": PEXELS_KEY}
for term in data["broll"]:
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": term, "per_page": 1, "orientation": "landscape"}
    )
    videos = r.json().get("videos", [])
    if videos:
        files = videos[0]["video_files"]
        sd = next((f for f in files if f["quality"] == "sd"), files[0])
        clip_path = f"clip_{len(clips)}.mp4"
        with open(clip_path, "wb") as f:
            f.write(requests.get(sd["link"]).content)
        clips.append(clip_path)
        print(f"  ✅ Downloaded: {term}")

if not clips:
    raise Exception("No Pexels clips downloaded — check your PEXELS_KEY secret")

# ── STEP 4: RENDER VIDEO WITH FFMPEG ────────────────
print("⚙️ Rendering video with FFmpeg...")
with open("clips.txt", "w") as f:
    for clip in clips:
        f.write(f"file '{clip}'\n")

subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", "clips.txt",
                "-c", "copy", "broll.mp4", "-y"], check=True)
subprocess.run(["ffmpeg", "-i", "broll.mp4", "-i", "voice.mp3",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", "final_video.mp4", "-y"], check=True)
print("✅ final_video.mp4 rendered")

# ── STEP 5: GENERATE THUMBNAIL ───────────────────────
print("🖼️ Generating thumbnail with Pollinations...")
prompt_enc = urllib.parse.quote(data["thumbnail_prompt"])
thumb_url = f"https://image.pollinations.ai/prompt/{prompt_enc}?width=1280&height=720&nologo=true"
thumb = requests.get(thumb_url, timeout=60)
with open("thumbnail.jpg", "wb") as f:
    f.write(thumb.content)
print("✅ thumbnail.jpg saved")

# ── STEP 6: UPLOAD TO YOUTUBE ────────────────────────
print("📤 Uploading to YouTube...")
from google.auth.transport.requests import Request

creds = Credentials(
    token=YT_TOKEN["token"],
    refresh_token=YT_TOKEN["refresh_token"],
    token_uri=YT_TOKEN["token_uri"],
    client_id=YT_TOKEN["client_id"],
    client_secret=YT_TOKEN["client_secret"],
    scopes=YT_TOKEN["scopes"]
)
# Auto-refresh if expired
if creds.expired or not creds.valid:
    creds.refresh(Request())
youtube = build("youtube", "v3", credentials=creds)

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
upload = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
video_id = upload["id"]
print(f"✅ Uploaded! https://youtube.com/watch?v={video_id}")

# ── SET THUMBNAIL ─────────────────────────────────────
youtube.thumbnails().set(
    videoId=video_id,
    media_body=MediaFileUpload("thumbnail.jpg")
).execute()
print("✅ Thumbnail set!")
print(f"\n🎉 DONE — https://youtube.com/watch?v={video_id}")
