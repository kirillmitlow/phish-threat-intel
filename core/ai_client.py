import os
import base64
import mimetypes
import time
import requests
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_API_URL = os.getenv("AI_BASE_URL", "http://deepcode.ci.nsu.ru/api/chat/completions")
DEFAULT_API_KEY = os.getenv("AI_API_KEY", "")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "Qwen3.8-27B")
DEFAULT_VLM_MODEL = os.getenv("DEFAULT_VLM_MODEL", "Qwen3.8-27B")


def get_chat_model(
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = 0.7,
    api_key: str = DEFAULT_API_KEY,
    api_url: str = DEFAULT_API_URL
) -> ChatOpenAI:
    base_url = api_url.replace("/chat/completions", "")
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout=180.0,
        max_retries=2
    )


def encode_image(image_path: str) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Файл изображения не найден: {image_path}")
    with open(image_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def ask_llm(
    prompt: str,
    system_prompt: str = "",
    model: str = DEFAULT_LLM_MODEL,
    api_key: str = DEFAULT_API_KEY,
    api_url: str = DEFAULT_API_URL,
    temperature: float = 0.7
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    last_err = None
    result = {}
    for attempt in range(3):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=90)
            if response.status_code in (502, 503, 504, 429) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            result = response.json()
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_err

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"]
    elif "output_text" in result:
        return result["output_text"]
    elif "response" in result:
        return result["response"]
    else:
        return str(result)


def ask_vlm(
    prompt: str,
    image_path: str,
    system_prompt: str = "",
    model: str = DEFAULT_VLM_MODEL,
    api_key: str = DEFAULT_API_KEY,
    api_url: str = DEFAULT_API_URL,
    temperature: float = 0.7
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    base64_data = encode_image(image_path)
    
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"

    image_data_url = f"data:{mime_type};base64,{base64_data}"

    user_content = [
        {
            "type": "text",
            "text": prompt
        },
        {
            "type": "image_url",
            "image_url": {
                "url": image_data_url
            }
        }
    ]

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    last_err = None
    result = {}
    for attempt in range(3):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=90)
            if response.status_code in (502, 503, 504, 429) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            result = response.json()
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_err

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"]
    elif "output_text" in result:
        return result["output_text"]
    elif "response" in result:
        return result["response"]
    else:
        return str(result)
