```toml
name = 'Meta: Llama 3 70B Instruct'
method = 'POST'
url = 'https://openrouter.ai/api/v1/chat/completions'
sortWeight = 4000000
id = 'd9a4df1a-784f-4db3-a4db-de813fb599c1'

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
  "model": "meta-llama/llama-3-70b-instruct",
  "frequency_penalty": 0,
  "presence_penalty": 0,
  "temperature": 0.5,
  "top_p": 0.5
}'''
```
