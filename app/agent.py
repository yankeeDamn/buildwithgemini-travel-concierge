# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-01-e4d70b5363d0"
BUCKET_NAME = "travel-concierge-assets-qwiklabs-gcp-01-e4d70b5363d0"
COLLECTION_NAME = "destinations"

try:
    with open(os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")) as f:
        AGENT_ENGINE_ID = json.load(f).get("remote_agent_runtime_id")
except Exception:
    AGENT_ENGINE_ID = "projects/1037399019344/locations/us-east1/reasoningEngines/110256827010121728"


def get_weather(query: str) -> str:
    """Fetches real-time current weather and temperature for any city worldwide using the Open-Meteo API.

    Args:
        query: Name of the city or location to get weather information for (e.g. 'Kyoto', 'Paris', 'San Francisco', 'Tokyo').

    Returns:
        A string with live weather, temperature, and wind speed details.
    """
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(query)}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "ADK-Agent/1.0"})
        with urllib.request.urlopen(req) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return f"Could not find geographic coordinates for '{query}'."

        loc_info = geo_data["results"][0]
        lat = loc_info["latitude"]
        lon = loc_info["longitude"]
        city_name = loc_info.get("name", query)
        country = loc_info.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "ADK-Agent/1.0"})
        with urllib.request.urlopen(req_w) as resp_w:
            w_data = json.loads(resp_w.read().decode())

        curr = w_data.get("current_weather", {})
        temp_c = curr.get("temperature")
        if temp_c is None:
            return f"Could not retrieve weather data for {city_name}."

        temp_f = round((temp_c * 9 / 5) + 32, 1)
        wind = curr.get("windspeed", 0)
        location_str = f"{city_name}, {country}" if country else city_name
        return f"Current weather in {location_str}: {temp_c}°C ({temp_f}°F), wind speed {wind} km/h."
    except Exception as e:
        return f"Error fetching live weather for '{query}': {str(e)}"


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def get_destination_details(destination_id: str) -> str | dict:
    """Retrieves detailed information about a specific travel destination from Firestore.

    Args:
        destination_id: The unique ID or slug of the destination (e.g. 'kyoto', 'paris', 'san-francisco').

    Returns:
        A dictionary containing destination details or an error string if not found.
    """
    db = firestore.Client(project=PROJECT_ID)
    slug = destination_id.lower().strip()
    doc_ref = db.collection(COLLECTION_NAME).document(slug)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()

    # Search by name if doc ID match is not found
    query_docs = (
        db.collection(COLLECTION_NAME)
        .where("name", "==", destination_id.title())
        .stream()
    )
    for d in query_docs:
        return d.to_dict()

    return f"Destination '{destination_id}' not found in the Firestore catalog."


def list_destinations(category: str = "") -> list[dict]:
    """Lists travel destinations from the Firestore catalog, optionally filtered by category.

    Args:
        category: Optional category filter (e.g. 'Coastal & Culture', 'Historic & Zen', 'Art & Culinary'). Leave empty to list all.

    Returns:
        A list of destination dictionaries available in the catalog.
    """
    db = firestore.Client(project=PROJECT_ID)
    col_ref = db.collection(COLLECTION_NAME)
    if category:
        docs = col_ref.where("category", "==", category).stream()
    else:
        docs = col_ref.stream()

    return [doc.to_dict() for doc in docs]


def add_destination(
    id: str,
    name: str,
    country: str,
    category: str,
    description: str,
    recommended_days: int,
    budget_tier: str,
    highlights: list[str],
) -> str:
    """Adds a new destination or updates an existing one in the Firestore travel catalog.

    Args:
        id: Unique identifier slug for the destination (e.g., 'tokyo', 'barcelona').
        name: Full display name of the destination (e.g., 'Tokyo', 'Barcelona').
        country: Country where the destination is located.
        category: Travel category (e.g., 'Modern & Tech', 'Historic & Coastal').
        description: Short overview of the destination.
        recommended_days: Recommended stay duration in days.
        budget_tier: Estimated price level (e.g., '$', '$$', '$$$', '$$$$').
        highlights: Key attractions or activities list.

    Returns:
        Confirmation message upon successfully saving to Firestore.
    """
    db = firestore.Client(project=PROJECT_ID)
    data = {
        "id": id.lower().strip(),
        "name": name,
        "country": country,
        "category": category,
        "description": description,
        "recommended_days": recommended_days,
        "budget_tier": budget_tier,
        "highlights": highlights,
    }
    db.collection(COLLECTION_NAME).document(data["id"]).set(data)
    return f"Successfully saved destination '{name}' (ID: {data['id']}) in Firestore."


def get_exchange_rates(from_currency: str = "USD", to_currencies: str = "EUR,JPY,GBP,ZAR") -> str:
    """Fetches real-time foreign exchange rates for travel budget planning.

    Args:
        from_currency: 3-letter currency code to convert from (e.g. 'USD', 'EUR', 'GBP').
        to_currencies: Comma-separated 3-letter target currency codes (e.g. 'EUR,JPY,GBP,ZAR').

    Returns:
        A string summary of live exchange rates.
    """
    try:
        base = from_currency.upper().strip()
        symbols = ",".join([c.strip().upper() for c in to_currencies.split(",") if c.strip()])
        api_key = os.getenv("EXCHANGE_RATE_API_KEY")
        if api_key:
            url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
        else:
            url = f"https://api.frankfurter.dev/v1/latest?base={base}&symbols={symbols}"

        req = urllib.request.Request(url, headers={"User-Agent": "ADK-Agent/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        rates = data.get("rates", {})
        if not rates:
            return f"Could not retrieve exchange rates from {base} to {to_currencies}."

        formatted_rates = [f"1 {base} = {rate} {symbol}" for symbol, rate in rates.items()]
        return f"Live exchange rates ({data.get('date', 'today')}): " + ", ".join(formatted_rates)
    except Exception as e:
        return f"Error fetching exchange rates: {str(e)}"


def geocode_address(address: str) -> dict | str:
    """Converts an address, landmark, or city name into geographic coordinates (latitude, longitude) and formatted address using Google Maps Geocoding API.

    Args:
        address: The address, place, or city name to geocode (e.g. 'Kyoto Station', 'Eiffel Tower, Paris').

    Returns:
        A dictionary containing formatted address and location coordinates (latitude, longitude), or an error string.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "ADK-Agent/1.0"})
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode())

        if res.get("status") != "OK" or not res.get("results"):
            return f"Geocoding failed for '{address}': {res.get('error_message', res.get('status'))}"

        first = res["results"][0]
        loc = first["geometry"]["location"]
        return {
            "address": first.get("formatted_address", address),
            "location": {"latitude": loc["lat"], "longitude": loc["lng"]},
        }
    except Exception as e:
        return f"Error geocoding address '{address}': {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: int = 2000,
) -> list[dict] | str:
    """Finds nearby places of interest (e.g., tourist attractions, restaurants, museums) around a geographic coordinate using Google Maps Places API (New).

    Args:
        latitude: Latitude of the center location.
        longitude: Longitude of the center location.
        place_type: Type of place to search for (e.g., 'tourist_attraction', 'restaurant', 'museum', 'cafe', 'park').
        radius_meters: Search radius in meters (default 2000m).

    Returns:
        A list of nearby place dictionaries with key fields (name, address, location, rating), or an error string.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.types",
        }
        body = {
            "includedTypes": [place_type],
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode())

        places = res.get("places", [])
        if not places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m."

        results = []
        for p in places:
            name = p.get("displayName", {}).get("text", "Unknown")
            address = p.get("formattedAddress", "")
            loc = p.get("location", {})
            rating = p.get("rating")
            results.append({
                "name": name,
                "address": address,
                "location": loc,
                "rating": rating,
            })
        return results
    except Exception as e:
        return f"Error finding nearby places: {str(e)}"


def generate_destination_image(prompt: str, tool_context: ToolContext = None) -> str:
    """Generates a high-quality visual preview image for a travel destination or landmark using gemini-3.1-flash-lite-image in the global region. Saves the image as a session artifact and uploads it to public Cloud Storage.

    Args:
        prompt: Visual description of the destination, scene, or landmark to generate (e.g., 'To-ji Temple pagoda in Kyoto surrounded by cherry blossoms').
        tool_context: Context injected by ADK to record session artifacts.

    Returns:
        The public Cloud Storage HTTPS URL of the generated image.
    """
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        res = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"Generate a photo of {prompt}",
        )

        part = res.candidates[0].content.parts[0]
        img_bytes = part.inline_data.data
        mime_type = part.inline_data.mime_type or "image/jpeg"
        ext = "jpg" if "jpeg" in mime_type else "png"

        filename = f"destination_{uuid.uuid4().hex[:8]}.{ext}"

        # (1) Save artifact for Playground Artifacts panel
        if tool_context:
            artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload directly from memory to public Cloud Storage bucket
        gcs_client = storage.Client(project=PROJECT_ID)
        bucket = gcs_client.bucket(BUCKET_NAME)
        blob_path = f"destinations/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(img_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}"
        return f"Successfully generated destination image. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating image: {str(e)}"


def generate_destination_video(prompt: str, tool_context: ToolContext = None) -> str:
    """Generates a short video for a travel destination using Google's Omni model (gemini-omni-flash-preview) in the global region. Saves the video as a session artifact and uploads it to public Cloud Storage.

    Args:
        prompt: Visual description of the destination, scene, or landmark to generate (e.g., 'A cinematic shot of a futuristic neon city with flying cars, cyberpunk style.').
        tool_context: Context injected by ADK to record session artifacts.

    Returns:
        The public Cloud Storage HTTPS URL of the generated video.
    """
    try:
        import base64
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a short video of {prompt}",
            response_format={"type": "video", "aspect_ratio": "16:9"}
        )
        
        if not interaction.output_video or not interaction.output_video.data:
            return "Error: No video data returned from the model."
            
        video_bytes = base64.b64decode(interaction.output_video.data) if isinstance(interaction.output_video.data, str) else interaction.output_video.data
        mime_type = "video/mp4"
        filename = f"destination_video_{uuid.uuid4().hex[:8]}.mp4"

        # (1) Save artifact for Playground Artifacts panel
        if tool_context:
            artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload directly from memory to public Cloud Storage bucket
        gcs_client = storage.Client(project=PROJECT_ID)
        bucket = gcs_client.bucket(BUCKET_NAME)
        blob_path = f"destinations_videos/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}"
        return f"Successfully generated destination video. Public URL: {public_url}"
    except Exception as e:
        return f"Error generating video: {str(e)}"


async def generate_memories_callback(callback_context: CallbackContext):
    """Sends the session's events to Memory Bank for memory generation."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are Travel Concierge, a helpful AI travel planning assistant. You can check weather, view timezone times, check live exchange rates, geocode addresses/locations, search nearby places using Google Maps, generate visual preview images for destinations, and browse or add destinations in your Firestore catalog database.\n\nCRITICAL: To run Python code, DO NOT attempt to call a tool named `run_code` or `codeExecution`. You MUST output the code directly in a markdown code block (starting with ```python and ending with ```). The system will automatically extract and execute the markdown block.",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        client_kwargs={"vertexai": True, "project": PROJECT_ID, "location": "us-east1"},
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=AgentEngineSandboxCodeExecutor(agent_engine_resource_name=AGENT_ENGINE_ID),
    tools=[
        get_weather,
        get_current_time,
        get_destination_details,
        list_destinations,
        add_destination,
        get_exchange_rates,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        generate_destination_video,
        PreloadMemoryTool(),
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=AGENT_ENGINE_ID.split("/")[-1],
    )

app = App(
    root_agent=root_agent,
    name="app",
    memory_service_builder=memory_bank_service_builder,
)




