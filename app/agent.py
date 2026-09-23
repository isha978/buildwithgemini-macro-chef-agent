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

import base64

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback


import io
import json
import os
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw
from google.cloud import firestore, storage

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-4b6f07bf9464"
GCS_BUCKET_NAME = "macro-chef-recipes-qwiklabs-gcp-02-4b6f07bf9464"
AGENT_ENGINE_RESOURCE_NAME = "projects/582175942571/locations/us-east1/reasoningEngines/6808222178677358592"

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are the Personal Dietary & Macro Chef agent. "
        "You help users plan healthy meals, calculate macronutrient breakdowns, discover existing recipes from your Firestore recipe database or real global recipes via TheMealDB API, create/store custom recipes, generate AI dish images with gemini-3.1-flash-lite-image, publish dish visual cards to Cloud Storage, and locate nearby grocery stores or ingredient suppliers via Maps Geocoding and Places APIs. "
        "Use `generate_recipe_image` to generate an AI dish image, save it to session artifacts, upload bytes directly to Cloud Storage, and return its public URL. "
        "Use `generate_recipe_video` to generate a short AI culinary video using gemini-omni-flash-preview, save it to session artifacts, upload bytes directly to Cloud Storage, and return its public URL. "
        "Use `geocode_address` to convert an address or location into coordinates. "
        "Use `find_nearby_places` to search for nearby supermarkets, grocery stores, or healthy restaurants around coordinates. "
        "Use `search_themealdb_recipes` to fetch real world global recipes and ingredient measurements from TheMealDB public API. "
        "Use `get_recipes_from_firestore` to query existing saved recipes in Firestore. "
        "Use `add_recipe_to_firestore` whenever the user asks to save or create a new recipe in their recipe database. "
        "Use `generate_dish_image` to generate and publish an image visual URL for any recipe. "
        "You remember stated user preferences, allergies, dietary constraints (e.g. keto, vegan, dairy-free, gluten-free), and target calorie/macro goals from previous conversations to personalize all future responses."
    ),
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


async def generate_memories_callback(callback_context: CallbackContext):
    """Write session events to Vertex AI Memory Bank at turn completion."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        pass
    return None


def calculate_macros(protein_g: float, carbs_g: float, fat_g: float) -> str:
    """Calculates total calories and macronutrient percentage breakdowns.

    Args:
        protein_g: Amount of protein in grams.
        carbs_g: Amount of carbohydrates in grams.
        fat_g: Amount of fat in grams.

    Returns:
        A string summarizing total calories and macro percentage split.
    """
    total_calories = (protein_g * 4) + (carbs_g * 4) + (fat_g * 9)
    if total_calories == 0:
        return "Total calories is 0."

    protein_pct = round(((protein_g * 4) / total_calories) * 100, 1)
    carbs_pct = round(((carbs_g * 4) / total_calories) * 100, 1)
    fat_pct = round(((fat_g * 9) / total_calories) * 100, 1)

    return (
        f"Total Calories: {round(total_calories, 1)} kcal | "
        f"Protein: {protein_g}g ({protein_pct}%), "
        f"Carbs: {carbs_g}g ({carbs_pct}%), "
        f"Fat: {fat_g}g ({fat_pct}%)"
    )


def search_recipes(ingredient_query: str, dietary_constraint: str = "") -> str:
    """Searches sample recipe database filtered by main ingredients and dietary needs.

    Args:
        ingredient_query: Comma-separated or single ingredient name to search.
        dietary_constraint: Optional dietary constraint (e.g., 'dairy-free', 'keto', 'vegan').

    Returns:
        Formatted string containing recipe options.
    """
    query = ingredient_query.lower()

    if "chicken" in query and "spinach" in query:
        return (
            "Found Recipe: Lemon Garlic Chicken & Spinach Skillet\n"
            "- Prep Time: 20 mins\n"
            "- Ingredients: Chicken breast, spinach, garlic, olive oil, lemon juice, salt, pepper\n"
            "- Macros per serving: 420 kcal, 45g Protein, 6g Carbs, 18g Fat\n"
            "- Dietary Compliance: Dairy-free, Gluten-free, Low-carb"
        )
    elif "salmon" in query or "fish" in query:
        return (
            "Found Recipe: Herb Crust Baked Salmon with Asparagus\n"
            "- Prep Time: 15 mins\n"
            "- Ingredients: Salmon fillet, asparagus, olive oil, herbs, lemon\n"
            "- Macros per serving: 510 kcal, 40g Protein, 4g Carbs, 32g Fat\n"
            "- Dietary Compliance: Dairy-free, Keto, Gluten-free"
        )
    return (
        f"Found Recipe: Custom Healthy Bowl for '{ingredient_query}' ({dietary_constraint})\n"
        "- Prep Time: 15 mins\n"
        "- Base: Mixed greens, lean protein, healthy fats, olive oil drizzle\n"
        "- Estimated Macros: 450 kcal, 35g Protein, 20g Carbs, 20g Fat"
    )


def search_themealdb_recipes(meal_name: str) -> str:
    """Searches the free public TheMealDB API for real recipe ideas, ingredients, and instructions by meal or ingredient name.

    Args:
        meal_name: Name of the meal or main ingredient to search (e.g. 'chicken', 'salmon', 'arrabiata', 'curry').

    Returns:
        Formatted summary of real recipes fetched from TheMealDB public API.
    """
    api_key = os.environ.get("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(meal_name)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            meals = data.get("meals")

        if not meals:
            return f"No recipes found on TheMealDB for '{meal_name}'."

        results = []
        for m in meals[:3]:
            ingredients = []
            for i in range(1, 21):
                ing = m.get(f"strIngredient{i}")
                meas = m.get(f"strMeasure{i}")
                if ing and ing.strip():
                    measure_str = f" ({meas.strip()})" if meas and meas.strip() else ""
                    ingredients.append(f"{ing.strip()}{measure_str}")

            instructions = m.get("strInstructions", "").replace("\r\n", " ").strip()
            results.append(
                f"• {m.get('strMeal')} [{m.get('strCategory')} / {m.get('strArea')}]\n"
                f"  - Ingredients: {', '.join(ingredients[:8])}\n"
                f"  - Instructions: {instructions[:200]}..."
            )

        return f"Real Recipes from TheMealDB ({len(meals)} total found):\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"Error fetching recipes from TheMealDB API: {str(e)}"


def get_recipes_from_firestore(category: str = "", dietary_tag: str = "") -> str:
    """Reads recipes from the Firestore database filtered by category or dietary tag.

    Args:
        category: Optional category filter (e.g., 'Breakfast', 'Lunch', 'Dinner').
        dietary_tag: Optional dietary tag filter (e.g., 'dairy-free', 'vegan', 'keto').

    Returns:
        Formatted summary of recipes found in Firestore.
    """
    try:
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        recipes_ref = db.collection("recipes")
        docs = recipes_ref.stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            tags = [t.lower() for t in data.get("dietary_tags", [])]
            recipe_cat = data.get("category", "").lower()

            if category and category.lower() not in recipe_cat:
                continue
            if dietary_tag and dietary_tag.lower() not in tags:
                continue

            results.append(
                f"• [{doc_id}] {data.get('title')} ({data.get('category')})\n"
                f"  - Prep Time: {data.get('prep_time_mins')} mins | Calories: {data.get('calories')} kcal\n"
                f"  - Macros: {data.get('protein_g')}g Protein, {data.get('carbs_g')}g Carbs, {data.get('fat_g')}g Fat\n"
                f"  - Tags: {', '.join(data.get('dietary_tags', []))}\n"
                f"  - Ingredients: {', '.join(data.get('ingredients', []))}\n"
                f"  - Instructions: {data.get('instructions')}"
            )

        if not results:
            return f"No recipes found in Firestore matching category='{category}' and tag='{dietary_tag}'."
        return f"Recipes in Firestore ({len(results)} found):\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"Error querying Firestore recipes: {str(e)}"


def add_recipe_to_firestore(
    title: str,
    category: str,
    prep_time_mins: int,
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    dietary_tags: str,
    ingredients: str,
    instructions: str,
) -> str:
    """Saves a new custom recipe to the Firestore database.

    Args:
        title: Title of the recipe.
        category: Category (e.g., 'Breakfast', 'Lunch', 'Dinner', 'Snack').
        prep_time_mins: Preparation time in minutes.
        calories: Estimated total calories in kcal.
        protein_g: Protein content in grams.
        carbs_g: Carbohydrate content in grams.
        fat_g: Fat content in grams.
        dietary_tags: Comma-separated list of dietary tags (e.g., 'dairy-free, vegan').
        ingredients: Comma-separated list of ingredients.
        instructions: Preparation instructions string.

    Returns:
        Confirmation message with the created Firestore document ID.
    """
    try:
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)
        doc_id = title.lower().replace(" ", "-").replace("&", "and")
        doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")

        tag_list = [t.strip().lower() for t in dietary_tags.split(",") if t.strip()]
        ing_list = [i.strip() for i in ingredients.split(",") if i.strip()]

        recipe_data = {
            "title": title,
            "category": category,
            "prep_time_mins": prep_time_mins,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "dietary_tags": tag_list,
            "ingredients": ing_list,
            "instructions": instructions,
        }

        db.collection("recipes").document(doc_id).set(recipe_data)
        return f"Successfully added recipe '{title}' to Firestore with ID 'recipes/{doc_id}'!"
    except Exception as e:
        return f"Error adding recipe to Firestore: {str(e)}"


def generate_dish_image(recipe_title: str, dish_description: str) -> str:
    """Generates an appetizing visual presentation card for a recipe, uploads it to public Cloud Storage, and returns the public image URL.

    Args:
        recipe_title: Title of the recipe (e.g. 'Avocado Protein Bowl').
        dish_description: Brief description of the dish visual presentation or main ingredients.

    Returns:
        Publicly accessible HTTP URL of the generated dish image.
    """
    try:
        img = Image.new("RGB", (650, 420), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        draw.rectangle([15, 15, 635, 405], outline=(74, 222, 128), width=3)
        draw.rectangle([15, 15, 635, 65], fill=(30, 41, 59))

        draw.text((30, 30), "MACRO CHEF • DISH VISUAL PRESENTATION", fill=(74, 222, 128))
        draw.text((30, 95), recipe_title[:45], fill=(255, 255, 255))

        words = dish_description.split()
        lines = []
        curr_line = ""
        for word in words:
            if len(curr_line) + len(word) + 1 <= 50:
                curr_line += (" " if curr_line else "") + word
            else:
                lines.append(curr_line)
                curr_line = word
        if curr_line:
            lines.append(curr_line)

        y_offset = 150
        for line in lines[:4]:
            draw.text((30, y_offset), f"• {line}", fill=(226, 232, 240))
            y_offset += 35

        draw.text((30, 360), "✓ Verified Macro Recipe • Hosted on Google Cloud Storage", fill=(148, 163, 184))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = client.bucket(GCS_BUCKET_NAME)
        doc_id = recipe_title.lower().replace(" ", "-").replace("&", "and")
        doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
        blob = bucket.blob(f"dishes/{doc_id}.png")
        blob.upload_from_file(buf, content_type="image/png")

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/dishes/{doc_id}.png"
        return f"Successfully generated and published dish image for '{recipe_title}'!\nPublic Image URL: {public_url}"
    except Exception as e:
        return f"Error generating dish image: {str(e)}"


async def generate_recipe_image(
    recipe_title: str,
    image_prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates an image for a recipe item in the agent's domain using gemini-3.1-flash-lite-image model in global region, saves it as an artifact in the session, uploads the image bytes directly to public Cloud Storage, and returns the public HTTP URL.

    Args:
        recipe_title: Title or name of the recipe item (e.g. 'Keto Chicken Avocado Salad').
        image_prompt: Visual description for generating the dish image.
        tool_context: ADK ToolContext injected automatically at runtime.

    Returns:
        Public HTTP URL of the generated image in Cloud Storage.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"High-quality food photo of {recipe_title}: {image_prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        img_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    img_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not img_bytes:
            return f"Failed to generate image for '{recipe_title}' (no image bytes returned)."

        doc_id = recipe_title.lower().replace(" ", "-").replace("&", "and")
        doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{doc_id}.{ext}"

        # 1. Save artifact with await tool_context.save_artifact so it shows in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"dishes/{filename}")
        blob.upload_from_string(img_bytes, content_type=mime_type)

        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/dishes/{filename}"
    except Exception as e:
        return f"Error generating recipe image: {str(e)}"


async def generate_recipe_video(
    recipe_title: str,
    video_prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a short video for a recipe item in the agent's domain using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the video as a Playground session artifact and uploads it to public Cloud Storage bucket.

    Args:
        recipe_title: Title or name of the recipe item (e.g. 'Keto Garlic Butter Steak').
        video_prompt: Visual motion description for generating the dish video clip.
        tool_context: ADK ToolContext injected automatically at runtime.

    Returns:
        Public HTTP URL of the generated video in Cloud Storage.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"High-quality culinary video of {recipe_title}: {video_prompt}",
        )

        video_bytes = None
        mime_type = "video/mp4"

        if response.output_video:
            data = response.output_video.data
            mime_type = response.output_video.mime_type or "video/mp4"
            if isinstance(data, str):
                video_bytes = base64.b64decode(data)
            elif isinstance(data, bytes):
                video_bytes = data

        if not video_bytes:
            return f"Failed to generate video for '{recipe_title}' (no video bytes returned)."

        doc_id = recipe_title.lower().replace(" ", "-").replace("&", "and")
        doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
        ext = "mp4" if "mp4" in mime_type else "mov"
        filename = f"{doc_id}.{ext}"

        # 1. Save artifact with await tool_context.save_artifact so it shows in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes directly to public GCS bucket (no writing to local file)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"videos/{filename}")
        blob.upload_from_string(video_bytes, content_type=mime_type)

        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/videos/{filename}"
    except Exception as e:
        return f"Error generating recipe video: {str(e)}"


def geocode_address(address: str) -> str:
    """Converts a street address or location name into geographical coordinates (latitude/longitude) using Google Geocoding API.

    Args:
        address: Street address or location query (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'Brisbane, Australia').

    Returns:
        Formatted location summary with name, address, and coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])

        if not results:
            return f"No geocoding results found for '{address}'."

        first = results[0]
        formatted_address = first.get("formatted_address", address)
        lat = first["geometry"]["location"]["lat"]
        lng = first["geometry"]["location"]["lng"]

        return (
            f"Geocoding Result for '{address}':\n"
            f"• Formatted Address: {formatted_address}\n"
            f"• Location Coordinates: ({lat}, {lng})"
        )
    except Exception as e:
        return f"Error calling Geocoding API: {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "supermarket",
    radius_meters: float = 5000.0,
) -> str:
    """Finds nearby places of a given type around a coordinate center using Google Places API (New).

    Args:
        latitude: Target center latitude coordinate.
        longitude: Target center longitude coordinate.
        place_type: Place type filter (e.g., 'supermarket', 'grocery_store', 'restaurant', 'health').
        radius_meters: Search radius in meters (default 5000.0).

    Returns:
        Formatted summary of key fields (name, address, location coordinates) for nearby places.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types",
    }
    body = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters,
            }
        },
    }

    try:
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            places = data.get("places", [])

        if not places:
            return f"No nearby '{place_type}' places found within {radius_meters}m of ({latitude}, {longitude})."

        results = []
        for p in places:
            name = p.get("displayName", {}).get("text", "N/A")
            addr = p.get("formattedAddress", "N/A")
            loc = p.get("location", {})
            results.append(
                f"• Name: {name}\n"
                f"  - Address: {addr}\n"
                f"  - Location: ({loc.get('latitude')}, {loc.get('longitude')})"
            )

        return f"Nearby '{place_type}' Places ({len(places)} found):\n\n" + "\n\n".join(results)
    except Exception as e:
        return f"Error calling Places API (New): {str(e)}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        calculate_macros,
        search_recipes,
        search_themealdb_recipes,
        get_recipes_from_firestore,
        add_recipe_to_firestore,
        generate_dish_image,
        generate_recipe_image,
        generate_recipe_video,
        geocode_address,
        find_nearby_places,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
