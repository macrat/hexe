curl -N https://api.openai.com/v1/chat/completions -H 'Content-Type: application/json' -H "Authorization: Bearer ${OPENAI_API_KEY}" -d '{
"model":"gpt-4-1106-preview",
"messages":[
    {
        "role": "user",
        "content": "Please show me a cat picture and a dog picture."
    }
],
"tools": [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string"
                    }
                },
                "required": ["prompt"]
            }
        }
    }
],
"stream": true
}'
