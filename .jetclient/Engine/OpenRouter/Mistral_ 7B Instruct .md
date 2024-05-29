```toml
name = 'Mistral: 7B Instruct '
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 6000000
id = '0271fa95-5520-4c34-8f4c-3de5650d2ef5'

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
  "model": "mistralai/mistral-7b-instruct",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
