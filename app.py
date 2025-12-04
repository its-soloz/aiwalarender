#!/usr/bin/env python3
"""
Kyvex Universal API Gateway - Render Deployment Version
Supports all models, parameters, and features found in the CLI.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import uuid
import json
import re
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
API_URL = "https://kyvex.ai/api/v1/ai/stream"
# Render sets PORT as environment variable
PORT = int(os.environ.get('PORT', 10000))

# Mapping friendly names/IDs to internal API model slugs
MODEL_MAP = {
    # Shortcuts / IDs
    "1": "kyvex",
    "2": "claude-sonnet-4.5",
    "3": "gpt-5",
    "4": "gemini-2.5-pro",
    "5": "grok-4",
    "6": "gemini-imagen-4",
    # Name matching
    "kyvex": "kyvex",
    "claude": "claude-sonnet-4.5",
    "sonnet": "claude-sonnet-4.5",
    "gpt5": "gpt-5",
    "gpt-5": "gpt-5",
    "gemini": "gemini-2.5-pro",
    "grok": "grok-4",
    "imagen": "gemini-imagen-4",
    "default": "kyvex"
}

# ==============================================================================
# HELPERS
# ==============================================================================
def random_user_agent():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"

def str_to_bool(val):
    """Converts 'true', '1', 'on' to boolean True."""
    if not val: return False
    return str(val).lower() in ('true', '1', 'on', 'yes')

def clean_token(text: str) -> str:
    """Cleans raw stream tokens."""
    if not text: return ""
    text = text.replace('\\n', '\n').replace('\\t', '\t')
    text = re.sub(r'^"|"$', '', text)
    text = text.replace('\\"', '"')
    return text

def process_imagen_specific(params):
    """
    Specific handler for Gemini Imagen 4 model using the exact configuration
    that was verified to work in debug_api.py.
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Brave\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-gpc": "1",
        "referrer": "https://kyvex.ai/",
        "referrerPolicy": "strict-origin-when-cross-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    
    cookies = {"browserId": f"BRWS-{uuid.uuid4().hex}"}
    
    payload = {
        "model": "gemini-imagen-4",
        "prompt": params.get('prompt', ''),
        "webSearch": False,
        "generateImage": True,
        "reasoning": False,
        "files": [],
        "inputAudio": "",
        "autoRoute": False
    }

    full_response = ""
    images = []

    try:
        with requests.post(API_URL, json=payload, headers=headers, cookies=cookies, stream=True, timeout=120) as resp:
            resp.encoding = 'utf-8'
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error_code": resp.status_code,
                    "message": resp.text[:300]
                }

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line: continue
                
                content = raw_line.strip()
                if content.startswith("data:"): content = content[len("data:"):].strip()
                if content == "[DONE]": break
                
                chunk = content
                try:
                    if content.startswith("{") or content.startswith("["):
                        data = json.loads(content)
                        if isinstance(data, dict):
                            if "token" in data: chunk = data["token"]
                            elif "content" in data: chunk = data["content"]
                            
                            if data.get("imageUrl"): 
                                images.append({"type": "url", "data": data["imageUrl"]})
                            if data.get("imageBase64"): 
                                images.append({"type": "base64", "data": data["imageBase64"]})
                    elif content.startswith('"') and content.endswith('"'):
                         chunk = json.loads(content)
                except:
                    pass

                # Regex fallback
                b64_m = re.search(r"base64,([A-Za-z0-9+/=]+)", chunk)
                if b64_m: 
                    images.append({"type": "base64", "data": b64_m.group(1)})
                
                url_m = re.search(r'(https://[^\s\'\")]+)', chunk)
                if url_m and ("api/files" in url_m.group(1) or url_m.group(1).lower().endswith((".png", ".jpg", ".jpeg"))):
                    images.append({"type": "url", "data": url_m.group(1)})

                full_response += clean_token(chunk)

    except Exception as e:
        return {"success": False, "message": str(e)}

    return {
        "success": True,
        "meta": {
            "model": "gemini-imagen-4",
            "web_search": False,
            "generated_image": True,
            "reasoning": False
        },
        "response": full_response.strip(),
        "thought": "",
        "images": images
    }

# ==============================================================================
# CORE PROCESSING
# ==============================================================================
def process_kyvex_request(params):
    """
    Handles the connection to the upstream AI provider.
    Aggregates the streaming response into a single JSON object.
    """
    
    # 1. Prepare Headers & Cookies
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Brave\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-gpc": "1",
        "referrer": "https://kyvex.ai/",
        "referrerPolicy": "strict-origin-when-cross-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    # Unique session ID for every request to prevent context collision
    cookies = {"browserId": f"BRWS-{uuid.uuid4().hex}"}

    # 2. Build Payload from Params
    # Default to Kyvex if model not found
    model_input = params.get('model', 'kyvex').lower()
    selected_model = MODEL_MAP.get(model_input, model_input) # Fallback to input if not in map

    # Route to specific handler for Imagen
    if selected_model == "gemini-imagen-4":
        return process_imagen_specific(params)

    # Force image generation for imagen model
    generate_image = str_to_bool(params.get('image', False))
    if selected_model == "gemini-imagen-4":
        generate_image = True

    payload = {
        "prompt": params.get('prompt', ''),
        "model": selected_model,
        "webSearch": str_to_bool(params.get('web', False)),
        "generateImage": generate_image,
        "reasoning": str_to_bool(params.get('reasoning', False)),
        "autoRoute": str_to_bool(params.get('auto', False)),
        "inputAudio": "",
        "files": []
    }

    # 3. Stream & Aggregate
    full_response = ""
    full_thought = ""
    images = [] # List of {type: 'url'|'b64', data: ...}
    
    current_mode = "response" # 'response' or 'think'

    try:
        with requests.post(API_URL, json=payload, headers=headers, cookies=cookies, stream=True, timeout=120) as resp:
            resp.encoding = 'utf-8'
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error_code": resp.status_code,
                    "message": resp.text[:300]
                }

            for raw_line in resp.iter_lines(decode_unicode=True):
                line = raw_line.strip()
                if not line or line.startswith(":"): continue
                if line.startswith("data:"): line = line[len("data:"):].strip()
                if line == "[DONE]": break

                # Attempt to parse JSON event
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, dict):
                    # Check for API Errors
                    if data.get("status") == "error":
                        return {"success": False, "message": data.get("message") or "Unknown upstream error"}

                    # Extract Text Content
                    content = ""
                    if data.get("token") is not None:
                        content = data.get("token", "")
                    elif isinstance(data.get("content"), str):
                        content = data["content"]
                    
                    # Extract Images (Base64 or URL)
                    if data.get("imageBase64"):
                        images.append({"type": "base64", "data": data.get("imageBase64")})
                    if data.get("imageUrl"):
                        images.append({"type": "url", "data": data.get("imageUrl")})
                        
                    # Handle "Deep Thinking" Tags
                    if "<think>" in content:
                        current_mode = "think"
                        content = content.replace("<think>", "")
                    if "</think>" in content:
                        current_mode = "response"
                        content = content.replace("</think>", "")

                    token = clean_token(content)
                    
                    if current_mode == "think":
                        full_thought += token
                    else:
                        full_response += token
                
                # Handling raw string case (rare in this API but possible)
                elif isinstance(data, str):
                    full_response += clean_token(data)

    except Exception as e:
        return {"success": False, "message": str(e)}

    return {
        "success": True,
        "meta": {
            "model": selected_model,
            "web_search": payload["webSearch"],
            "generated_image": payload["generateImage"],
            "reasoning": payload["reasoning"]
        },
        "response": full_response.strip(),
        "thought": full_thought.strip(), # Will be empty if reasoning was off
        "images": images
    }

# ==============================================================================
# ROUTES
# ==============================================================================

@app.route('/chat/get', methods=['GET', 'POST'])
def chat_endpoint():
    """
    Main Endpoint.
    Accepts GET query params OR JSON POST body.
    
    Parameters:
    - prompt: The text to send.
    - model: 'gpt-5', 'kyvex', 'claude', 'gemini', 'grok' (or ID 1-6)
    - web: 'true' (Enables Web Search)
    - image: 'true' (Enables Image Gen)
    - reasoning: 'true' (Enables chain of thought)
    - auto: 'true' (Enables Auto-Routing)
    """
    
    # Handle inputs from either Query String (GET) or Body (POST)
    if request.method == 'POST':
        params = request.json or request.form
    else:
        params = request.args

    prompt = params.get('prompt')
    if not prompt:
        return jsonify({
            "success": False, 
            "message": "Missing 'prompt' parameter."
        }), 400

    # Process
    result = process_kyvex_request(params)
    
    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code

@app.route('/models', methods=['GET'])
def list_models():
    """List available model keys."""
    unique_models = list(set(MODEL_MAP.values()))
    return jsonify({
        "success": True, 
        "models": unique_models,
        "map": MODEL_MAP
    })

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "Online",
        "info": "Kyvex Universal API Gateway",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/chat/get?prompt=hi&model=gpt-5",
            "models": "/models"
        },
        "usage": {
            "GET": "?prompt=Your+text&model=gpt-5&web=true",
            "POST": {"prompt": "Your text", "model": "gpt-5", "web": True}
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({"status": "healthy", "service": "kyvex-api-gateway"}), 200

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    print(f"✨ Kyvex API Gateway running on port {PORT}")
    print(f"🚀 Ready to accept requests")
    # Bind to 0.0.0.0 so Render can access it
    app.run(host='0.0.0.0', port=PORT, debug=False)
