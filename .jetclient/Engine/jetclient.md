```toml
name = 'Engine'
description = '翻译引擎测试'
icon = 'MODULE_GROUP'
sortWeight = 1000000
id = '0cb8c080-07e8-4185-b5b6-85c6f97d043b'

[[environmentGroups]]
name = 'Default'
environments = []
```

#### Variables

```json5
{
 
}
```

#### Init Script

```js
const Files = Java.type('java.nio.file.Files');
const Paths = Java.type('java.nio.file.Paths');

// 获取 Prompt
const promptPath = Paths.get("/Users/likai/Github/Tools/RSS-Translator/.jetclient/Engine/Text/prompt.md");
const promptRaw = Files.readString(promptPath)
const PromptText = promptRaw.replace(/\n/g, '\\n').replace(/"/g, '\\"')


// 获取 Content
const contentPath = Paths.get("/Users/likai/Github/Tools/RSS-Translator/.jetclient/Engine/Text/content.md");
const contentRaw = Files.readString(contentPath)
const ContentText = contentRaw.replace(/\n/g, '\\n').replace(/"/g, '\\"')


try {
    jc.variables.set("ContentText", ContentText );
    jc.variables.set("PromptText", PromptText );
} catch (e) {
    console.error("Error reading file: " + e.message);
}
```
