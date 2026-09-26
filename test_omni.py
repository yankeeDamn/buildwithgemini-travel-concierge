import vertexai
from vertexai.generative_models import GenerativeModel
vertexai.init(project="qwiklabs-gcp-01-e4d70b5363d0", location="global")
model = GenerativeModel("gemini-omni-flash-preview")
try:
    response = model.generate_content("Generate a short video of a cat")
    print(response)
except Exception as e:
    print("Error:", e)
