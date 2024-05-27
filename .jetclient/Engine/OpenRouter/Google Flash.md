```toml
name = 'Google Flash'
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 1000000
id = 'ddb66634-da1d-4036-ad0b-29d2eb8f0ec6'

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
  "model": "google/gemini-flash-1.5",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
