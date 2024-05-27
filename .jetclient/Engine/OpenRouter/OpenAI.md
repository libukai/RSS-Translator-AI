```toml
name = 'OpenAI'
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 2000000
id = 'd0f773a9-5817-4735-ae6d-d3655f386293'

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
  "model": "openai/gpt-3.5-turbo",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
