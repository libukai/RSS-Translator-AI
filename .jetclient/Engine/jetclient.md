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

// 读取并处理文件内容的通用函数
function readFileAndProcess(filePath) {
    const path = Paths.get(filePath);
    const rawContent = Files.readString(path);
    return rawContent.replace(/\n/g, '\\n').replace(/"/g, '\\"');
}

try {
    // 获取 Prompt
    const promptFilePath = "/Users/likai/Github/Tools/RSS-Translator/.jetclient/Engine/Text/prompt-vietnamese.md";
    const PromptText = readFileAndProcess(promptFilePath);

    // 获取 Content
    const contentFilePath = "/Users/likai/Github/Tools/RSS-Translator/.jetclient/Engine/Text/vietnamese.md";
    const ContentText = readFileAndProcess(contentFilePath);

    // 设置变量
    jc.variables.set("ContentText", ContentText);
    jc.variables.set("PromptText", PromptText);
} catch (e) {
    console.error("Error Happend: " + e.message);
}
```
