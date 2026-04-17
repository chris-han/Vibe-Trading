import os
import requests
import json

api_key = "sk-bdc5e5ca198f4f5f88cadf1653b74acc"
# Standard OpenAI compatible chat completion endpoint
url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

def test_variant(name, payload):
    print(f"--- Testing Variant {name} ---")
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        choices = data.get("choices", [])
        output_text = ""
        if choices:
            output_text = choices[0].get("message", {}).get("content", "")

        print(f"Success: {response.status_code == 200 and 'error' not in data}")
        print(f"Output Text: {output_text}")
        
    except Exception as e:
        print(f"Error: {e}")
    print("\n")

# Use qwen-plus for OpenAI compatibility
model = "qwen-plus"

# Variant A: Hermes-like
payload_a = {
    "model": model,
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "store": False,
    "prompt_cache_key": "debug-test",
    # Reasoning might not be supported in standard chat/completions yet, but let's see
    "extra_body": {
        "reasoning": {"effort": "medium", "summary": "auto"},
        "include": ["reasoning.encrypted_content"]
    }
}

# Variant B: Same as A + dummy tool
payload_b = {
    "model": model,
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"]
                }
            }
        }
    ],
    "tool_choice": "auto"
}

# Variant C: Alibaba-doc-style thinking
payload_c = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one sentence."}
    ],
    "extra_body": {
        "enable_thinking": True
    }
}

# Variant D: Alibaba-doc-style without thinking
payload_d = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one sentence."}
    ]
}

test_variant("A", payload_a)
test_variant("B", payload_b)
test_variant("C", payload_c)
test_variant("D", payload_d)
