import logging
from django.db import models
from django.utils.translation import gettext_lazy as _
import cityhash
from config import settings
from openai import OpenAI
from encrypted_model_fields.fields import EncryptedCharField


class TranslatorEngine(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)
    valid = models.BooleanField(_("Valid"), null=True)
    is_ai = models.BooleanField(default=False, editable=False)

    def translate(
        self,
        text: str,
        target_language: str,
        translate_title: str,
        source_language: str = "auto",
        **kwargs,
    ) -> dict:
        raise NotImplementedError(
            "subclasses of TranslatorEngine must provide a translate() method"
        )

    def min_size(self) -> int:
        if hasattr(self, "max_characters"):
            return self.max_characters
        if hasattr(self, "max_tokens"):
            return self.max_tokens
        return 0

    def max_size(self) -> int:
        if hasattr(self, "max_characters"):
            return self.max_characters
        if hasattr(self, "max_tokens"):
            return self.max_tokens
        return 0

    def validate(self) -> bool:
        raise NotImplementedError(
            "subclasses of TranslatorEngine must provide a validate() method"
        )

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Translated_Content(models.Model):
    # hash = models.BinaryField(max_length=8, unique=True, primary_key=True, editable=False)
    hash = models.CharField(max_length=39, editable=False, primary_key=True)
    original_content = models.TextField()

    translated_language = models.CharField(max_length=255)
    translated_content = models.TextField()

    tokens = models.IntegerField(default=0)
    characters = models.IntegerField(default=0)

    def __str__(self):
        return self.original_content

    @classmethod
    def is_translated(cls, text, target_language):
        text_hash = str(cityhash.CityHash128(f"{text}{target_language}"))
        try:
            content = Translated_Content.objects.get(hash=text_hash)
            # logging.info("Using cached translations:%s", text)
            return {
                "text": content.translated_content,
                "tokens": content.tokens,
                "characters": content.characters,
            }
        except Translated_Content.DoesNotExist:
            logging.info("Does not exist in cache:%s", text)
            return None

    def save(self, *args, **kwargs):
        if not self.hash:
            self.hash = str(
                cityhash.CityHash128(
                    f"{self.original_content}{self.translated_language}"
                )
            )

        super(Translated_Content, self).save(*args, **kwargs)


class OpenAIInterface(TranslatorEngine):
    is_ai = models.BooleanField(default=True, editable=False)
    api_key = EncryptedCharField(_("API Key"), max_length=255)
    base_url = models.URLField(_("API URL"), default="https://api.openai.com/v1")
    model = models.CharField(
        max_length=100,
        default="gpt-3.5-turbo",
        help_text="e.g. gpt-3.5-turbo, gpt-4-turbo",
    )
    translate_prompt = models.TextField(
        _("Title Translate Prompt"), default=settings.default_title_translate_prompt
    )
    content_translate_prompt = models.TextField(
        _("Content Translate Prompt"), default=settings.default_content_translate_prompt
    )

    temperature = models.FloatField(default=0.2)
    top_p = models.FloatField(default=0.2)
    frequency_penalty = models.FloatField(default=0)
    presence_penalty = models.FloatField(default=0)
    max_tokens = models.IntegerField(default=2000)

    summary_prompt = models.TextField(default=settings.default_summary_prompt)

    class Meta:
        abstract = True

    def _init(self):
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120.0,
        )

    def validate(self) -> bool:
        if self.api_key:
            try:
                client = self._init()
                res = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                )
                fr = res.choices[
                    0
                ].finish_reason  # 有些第三方源在key或url错误的情况下，并不会抛出异常代码，而是返回html广告，因此添加该行。
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
        system_prompt: str = None,
        user_prompt: str = None,
        text_type: str = "title",
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

            prompt_title = "文章的标题：" + translate_title
            prompt_text = "段落的内容：" + text

            res = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://www.rsstranslator.com",
                    "X-Title": "RSS Translator",
                },
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_title},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=self.temperature,
                top_p=self.top_p,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
            )
            if res.choices[0].finish_reason == "stop" or res.choices[0].message.content:
                logging.info(
                    "OpenAITranslator->%s: %s", res.choices[0].finish_reason, text
                )
                translated_text = res.choices[0].message.content
                logging.info(
                    "OpenAITranslator->%s: %s",
                    res.choices[0].finish_reason,
                    translated_text,
                )
            # else:
            #     translated_text = ''
            #     logging.warning("Translator->%s: %s", res.choices[0].finish_reason, text)
            tokens = res.usage.total_tokens if res.usage else 0
        except Exception as e:
            logging.error("ErrorTranslator->%s: %s", e, text)

        return {"text": translated_text, "tokens": tokens}

    def summarize(self, text: str, target_language: str) -> dict:
        logging.info(">>> Summarize [%s]: %s", target_language, text)
        return self.translate(text, target_language, system_prompt=self.summary_prompt)
