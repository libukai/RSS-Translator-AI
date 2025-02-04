import logging

from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import OpenAIInterface


class OpenRouterAITranslator(OpenAIInterface):
    # https://openrouter.ai/docs
    base_url = models.URLField(_("API URL"), default="https://openrouter.ai/api/v1")
    model = models.CharField(
        max_length=100,
        default="openai/gpt-3.5-turbo",
        help_text="More models can be found at https://openrouter.ai/docs#models",
    )

    class Meta:
        verbose_name = "OpenRouter AI"
        verbose_name_plural = "OpenRouter AI"

    def validate(self) -> bool:
        if self.api_key:
            try:
                client = self._init()
                res = client.chat.completions.create(
                    # NOTE: 增加调用时的客户端标识
                    extra_headers={
                        "HTTP-Referer": "https://trans.10k.xyz",
                        "X-Title": "RSS-Translator",
                    },
                    model=self.model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                )
                fr = res.choices[0].finish_reason
                logging.info(">>> Translator Validate:%s", fr)
                return True
            except Exception as e:
                logging.error("OpenAIInterface validate ->%s", e)
                return False

    def translate(
        self,
        text: str,
        target_language: str,
        translate_title: str,
        text_type: str = "title",
        system_prompt: str = None,
        user_prompt: str = None,
    ) -> dict:
        logging.info(">>> Translate [%s]: %s", target_language, text)
        client = self._init()
        tokens = 0
        translated_text = ""
        system_prompt = (
            system_prompt or self.translate_prompt
            if text_type == "title"
            else self.content_translate_prompt
        )
        try:
            system_prompt = system_prompt.replace("{target_language}", target_language)
            if user_prompt:
                system_prompt += f"\n\n{user_prompt}"

            # 根据 text_type 构建不同的 messages
            if text_type == "title":
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ]
            else:
                prompt_title = "文章的标题：" + translate_title
                prompt_text = "段落的内容：" + text
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_title},
                    {"role": "user", "content": prompt_text},
                ]

            res = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://news.10k.xyz",
                    "X-Title": "RSS-Translator",
                },
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
            )
            if res.choices[0].finish_reason == "stop" or res.choices[0].message.content:
                translated_text = res.choices[0].message.content
                logging.info(
                    "OpenAITranslator->%s: %s",
                    res.choices[0].finish_reason,
                    translated_text,
                )
            # else:
            #     translated_text = ''
            #     logging.warning("Translator->%s: %s", res.choices[0].finish_reason, text)
            tokens = res.usage.total_tokens
        except Exception as e:
            logging.error("ErrorTranslator->%s: %s", e, text)

        return {"text": translated_text, "tokens": tokens}
