from google import genai
import base64
client = genai.Client(vertexai=True, project="qwiklabs-gcp-01-e4d70b5363d0", location="global")
res = client.interactions.create(
    model="gemini-omni-flash-preview",
    input="A scenic drone shot of a beach",
    response_format={"type": "video"}
)
print("Video data type:", type(res.output_video.data))
if res.output_video.data:
    data = base64.b64decode(res.output_video.data) if isinstance(res.output_video.data, str) else res.output_video.data
    print("Video size:", len(data))
else:
    print("No video data")
