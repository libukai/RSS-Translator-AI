```toml
name = 'Anthropic: Claude 3 Haiku'
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 3000000
id = '55fe07b4-e39f-43d7-b5dc-c4046b7e1954'

[body]
type = 'JSON'
raw = '''
{
  "messages": [
    {
      "role": "system",
      "content": "{{PromptText}}"
    },
    {
      "role": "user",
      "content": "{{ContentText}}"
    }
  ],
  "model": "anthropic/claude-3-haiku",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
