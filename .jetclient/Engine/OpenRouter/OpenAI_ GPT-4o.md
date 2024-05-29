```toml
name = 'OpenAI: GPT-4o'
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 7000000
id = '400cc857-7850-4d3f-97c9-cf016d66e59e'

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
  "model": "openai/gpt-4o",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
