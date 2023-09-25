curl -N https://api.openai.com/v1/chat/completions -H 'Content-Type: application/json' -H "Authorization: Bearer ${OPENAI_API_KEY}" -d '{
"model":"gpt-4",
"messages":[
    {
        "role": "system",
        "content": "Answer precisely. If user changes topic, call `save_notes` with summary of conversation until user changes topic, before answer them.\n\nCurrent datetime: 2023-08-28T23:03:00+09:00 (Mon)\nNotes:\n{\"saved_at\":\"2023-08-28T22:23:00+09:00\",\"note\":\"User is located in Setagaya ward, Tokyo\"}"
    },
    {
        "role": "user",
        "content": "明日の天気は？"
    },
    {
        "role": "assistant",
        "content": "すみませんが、私は直接的に天気情報を提供する能力はありません。ただし、インターネット上でお住まいの地域の天気予報を検索することはできます。では、お住まいの地域名を教えていただけますか？"
    },
    {
        "role": "user",
        "content": "世田谷区です。"
    },
    {
        "role": "assistant",
        "content": null,
        "function_call": {
            "name": "search_google",
            "arguments": "{\n  \"query\": \"世田谷区 明日の天気\"\n}"
        }
    },
    {
        "role": "function",
        "name": "search_google",
        "content": "[{\"title\":\"世田谷区の3時間天気 - 日本気象協会 tenki.jp\",\"url\":\"https://tenki.jp/forecast/3/16/4410/13112/3hours.html\"},{\"title\":\"世田谷区の今日明日の天気 - 日本気象協会 tenki.jp\",\"url\":\"https://tenki.jp/forecast/3/16/4410/13112/\"}]"
    },
    {
        "role": "assistant",
        "content": null,
        "function_call": {
            "name": "fetch_url",
            "arguments": "{\n  \"url\": \"https://tenki.jp/forecast/3/16/4410/13112/\"\n}"
        }
    },
    {
        "role": "function",
        "name": "fetch_url",
        "content": "日付\t\n今日 08月28日(月)[先勝]\n\n時刻\t午前\t午後\n03\t06\t09\t12\t15\t18\t21\t24\n天気\t曇り\n曇り\n\n曇り\n曇り\n\n曇り\n曇り\n\n曇り\n曇り\n\n曇り\n曇り\n\n曇り\n曇り\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n気温(℃)\t\n26.5\t26.0\t29.5\t32.5\t33.0\t30.5\t28.5\t27.6\n降水確率(%)\t---\t---\t---\t---\t---\t---\t---\t0\n降水量(mm/h)\t0\t0\t0\t0\t0\t0\t0\t0\n0\t0\t0\t0\t0\t0\t0\t0\n湿度(%)\t98\t93\t79\t63\t62\t71\t83\t85\n風向\t西南西\n西南西\n\n南南西\n南南西\n\n南南西\n南南西\n\n南\n南\n\n南南西\n南南西\n\n南南西\n南南西\n\n南\n南\n\n南南西\n南南西\n\n風速(m/s)\t1\t1\t1\t2\t2\t2\t1\t2\n\n雨雲レーダー\n雨雲レーダー\n天気図\n天気図\nアメダス\nアメダス\n警報・注意報\n警報・注意報\n日付\t\n明日 08月29日(火)[友引]\n\n時刻\t午前\t午後\n03\t06\t09\t12\t15\t18\t21\t24\n天気\t晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n気温(℃)\t\n26.7\t26.7\t30.8\t34.4\t32.8\t29.4\t28.0\t26.9\n降水確率(%)\t0\t10\t0\t0\t0\t0\t0\t0\n降水量(mm/h)\t0\t0\t0\t0\t0\t0\t0\t0\n0\t0\t0\t0\t0\t0\t0\t0\n湿度(%)\t89\t88\t68\t57\t59\t70\t77\t82\n風向\t南西\n南西\n\n南西\n南西\n\n南西\n南西\n\n南\n南\n\n南\n南\n\n南\n南\n\n南\n南\n\n南南西\n南南西\n\n風速(m/s)\t2\t1\t1\t2\t4\t4\t3\t2\n日付\t\n明後日 08月30日(水)[先負]\n\n時刻\t午前\t午後\n03\t06\t09\t12\t15\t18\t21\t24\n天気\t晴れ\n晴れ\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n曇り\n曇り\n\n晴れ\n晴れ\n\n晴れ\n晴れ\n\n曇り\n曇り\n\n晴れ\n晴れ\n\n気温(℃)\t\n26.1\t26.0\t30.4\t33.6\t32.2\t29.4\t28.2\t27.3\n降水確率(%)\t0\t0\t10\t20\t0\t0\t20\t0\n降水量(mm/h)\t0\t0\t0\t0\t0\t0\t0\t0\n0\t0\t0\t0\t0\t0\t0\t0\n湿度(%)\t87\t86\t69\t61\t63\t75\t83\t86\n風向\t南南西\n南南西\n\n西南西\n西南西\n\n南南西\n南南西\n\n南\n南\n\n南\n南\n\n南\n南\n\n南\n南\n\n南\n南\n\n風速(m/s)\t2\t1\t2\t3\t3\t3\t3\t3"
    },
    {
        "role": "assistant",
        "content": "世田谷区の明日（8月29日）の天気予報によれば、一日中晴れて最高気温は34.4度、最低気温は26.7度になる予定です。降水の可能性はなく、湿度は最低57%から最高82%、風向は南方向から南西方向の予報です。引き続き夏らしい暑い一日となりそうです。お出かけの際は、十分に水分補給を行うなど、熱中症対策を忘れずにお過ごしください。"
    },
    {
        "role": "user",
        "content": "猫の画像を生成してください。"
    }
],
"functions":[
    {
        "name": "save_notes",
        "description": "Save notes about what you learn from the conversation, including but not limited to, user profile, user preferences, and decisions made during the conversation.",
        "parameters": {
            "type": "object",
            "required": ["notes"],
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["note", "expire_days"],
                        "properties": {
                            "note": {
                                "desctiption": "The note to save.",
                                "type": "string"
                            },
                            "expire_days": {
                                "description": "The expire of the note, in days. 0 or negative means forever.",
                                "type": "integer"
                            }
                        }
                    },
                    "minItems": 1
                }
            }
        }
    },
    {
        "name": "search_google",
        "description": "Search the internet using Google.",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "fetch_url",
        "description": "Fetch the URL.",
        "parameters": {
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "generate_image",
        "description": "Generate image from a prompt and display it for user.",
        "parameters": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "description": "The prompt to generate the image, in English.",
                    "type": "string"
                }
            }
        }
    },
    {
        "name": "show_prompt",
        "description": "Mark the current message as done and show the prompt for user to respond.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]
}'
