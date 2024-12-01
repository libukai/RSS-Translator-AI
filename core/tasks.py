import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from time import mktime
from typing import Optional

import cityhash
import feedparser
import mistune
import newspaper
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import IntegrityError
from feed2json import feed2json
from huey.contrib.djhuey import HUEY as huey
from huey.contrib.djhuey import db_task, on_shutdown, on_startup

from translator.models import Translated_Content, TranslatorEngine
from utils import text_handler
from utils.feed_action import fetch_feed, generate_atom_feed

from .models import O_Feed, T_Feed

# from huey_monitor.models import TaskModel
unique_tasks = set()


def revoke_tasks_by_arg(arg_to_match):
    for task in huey.scheduled() + huey.pending():
        # Assuming the first argument is the one we're interested in (e.g., obj.pk)
        if task.args and task.args[0] == arg_to_match:
            logging.info("Revoke task: %s", task)
            huey.revoke_by_id(task)


# @periodic_task(crontab( minute='*/1'))
@on_startup()
def schedule_update():
    feeds = O_Feed.objects.all()
    tasks = huey.scheduled() + huey.pending()
    task_feeds = {task.args[0] for task in tasks if task.args}

    for feed in feeds:
        if feed.sid not in task_feeds:
            update_original_feed.schedule(
                args=(feed.sid,), delay=feed.update_frequency * 60
            )


@on_shutdown()
def cleanup_tasks():
    huey.storage.flush_all()


@db_task(retries=3)
def update_original_feed(sid: str, force: bool = False):
    if sid in unique_tasks:  # 如果判断force的话，是没法停止正在执行的task
        logging.warning("(skip)This task update_original_feed is executing: %s", sid)
        return
    else:
        unique_tasks.add(sid)

    try:
        # obj = O_Feed.objects.get(sid=sid)
        obj = O_Feed.objects.prefetch_related("t_feed_set").get(sid=sid)
    except O_Feed.DoesNotExist:
        return False

    revoke_tasks_by_arg(sid)
    logging.info("Call task update_original_feed: %s", obj.feed_url)

    feed_dir_path = Path(settings.DATA_FOLDER) / "feeds"

    if not os.path.exists(feed_dir_path):
        os.makedirs(feed_dir_path)

    original_feed_file_path = feed_dir_path / f"{obj.sid}.xml"
    try:
        obj.valid = False
        fetch_feed_results = fetch_feed(url=obj.feed_url, etag=obj.etag)
        error = fetch_feed_results["error"]
        update = fetch_feed_results.get("update")
        xml = fetch_feed_results.get("xml")
        feed = fetch_feed_results.get("feed")

        if error:
            raise Exception(f"Fetch Original Feed Failed: {error}")
        elif not update:
            logging.info("Original Feed is up to date, Skip:%s", obj.feed_url)
        else:
            with open(original_feed_file_path, "w", encoding="utf-8") as f:
                f.write(xml)
            if obj.name in ["Loading", "Empty", None]:
                obj.name = feed.feed.get("title") or feed.feed.get("subtitle")
            obj.size = os.path.getsize(original_feed_file_path)
            update_time = feed.feed.get("updated_parsed")
            obj.last_updated = (
                datetime.fromtimestamp(mktime(update_time), tz=timezone.utc)
                if update_time
                else None
            )
            # obj.last_pull = datetime.now(timezone.utc)
            obj.etag = feed.get("etag", "")

        obj.valid = True
        # update_original_feed.schedule(args=(obj.sid,), delay=obj.update_frequency * 60)
    except Exception as e:
        logging.exception("task update_original_feed %s: %s", obj.feed_url, str(e))
    finally:
        obj.last_pull = datetime.now(timezone.utc)
        update_original_feed.schedule(args=(obj.sid,), delay=obj.update_frequency * 60)
        obj.save()
        unique_tasks.remove(sid)

    # Update T_Feeds
    t_feeds = obj.t_feed_set.all()
    if obj.valid and t_feeds.exists():
        for t_feed in t_feeds:
            t_feed.status = None
            t_feed.save()
            update_translated_feed.schedule(args=(t_feed.sid,), delay=1)


@db_task(retries=3)
def update_translated_feed(sid: str, force: bool = False):
    if sid in unique_tasks:  # 如果判断force的话，是没法停止正在执行的task
        logging.warning("(skip)The task update_translated_feed is executing: %s", sid)
        return
    else:
        unique_tasks.add(sid)

    try:
        # obj = T_Feed.objects.get(sid=sid)
        obj = T_Feed.objects.select_related("o_feed").get(sid=sid)
    except T_Feed.DoesNotExist:
        logging.error(f"T_Feed Not Found: {sid}")
        return False

    try:
        revoke_tasks_by_arg(sid)
        logging.info("Call task update_translated_feed: %s", obj.o_feed.feed_url)

        if obj.o_feed.pk is None:
            raise Exception("Unable translate feed, because Original Feed is None")

        if not force and obj.modified == obj.o_feed.last_pull:
            logging.info(
                "Translated Feed is up to date, Skip translation: %s",
                obj.o_feed.feed_url,
            )
            obj.status = True
            obj.save()
            return True

        feed_dir_path = f"{settings.DATA_FOLDER}/feeds"
        if not os.path.exists(feed_dir_path):
            os.makedirs(feed_dir_path)

        original_feed_file_path = f"{feed_dir_path}/{obj.o_feed.sid}.xml"
        if not os.path.exists(original_feed_file_path):
            update_original_feed.call_local(obj.o_feed.sid)
            return False

        translated_feed_file_path = f"{feed_dir_path}/{obj.sid}"

        original_feed = feedparser.parse(original_feed_file_path)

        if original_feed.entries:
            o_feed = obj.o_feed
            logging.info("Start translate feed: [%s]%s", obj.language, o_feed.feed_url)
            results = translate_feed(
                feed=original_feed,
                target_language=obj.language,
                translate_engine=o_feed.translator,
                translate_title=obj.translate_title,
                translate_content=obj.translate_content,
                summary=obj.summary,
                summary_engine=o_feed.summary_engine,
                summary_detail=o_feed.summary_detail,
                max_posts=o_feed.max_posts,
                translation_display=o_feed.translation_display,
                quality=o_feed.quality,
                fetch_article=o_feed.fetch_article,
            )

            if not results:
                raise Exception("Translate Feed Failed")
            else:
                feed = results.get("feed")
                total_tokens = results.get("tokens")
                translated_characters = results.get("characters")
            xml_str = generate_atom_feed(
                o_feed.feed_url, feed
            )  # feed is a feedparser object

            if xml_str is None:
                raise Exception("generate_atom_feed returned None")
            with open(f"{translated_feed_file_path}.xml", "w", encoding="utf-8") as f:
                f.write(xml_str)

            json_dict = feed2json(f"{translated_feed_file_path}.xml")
            json_str = json.dumps(json_dict, indent=4, ensure_ascii=False)
            if json_str is None:
                logging.error("atom2json returned None")
            else:
                with open(
                    f"{translated_feed_file_path}.json", "w", encoding="utf-8"
                ) as f:
                    f.write(json_str)

            # There can only be one billing method at a time, either token or character count.
            if total_tokens > 0:
                obj.total_tokens += total_tokens
            else:
                obj.total_characters += translated_characters

            obj.modified = obj.o_feed.last_pull
            obj.size = os.path.getsize(f"{translated_feed_file_path}.xml")
            obj.status = True
    except Exception as e:
        logging.error(
            "task update_translated_feed (%s)%s: %s",
            obj.language,
            obj.o_feed.feed_url,
            str(e),
        )
        obj.status = False
    finally:
        obj.save()
        unique_tasks.remove(sid)


def translate_feed(
    feed: feedparser.FeedParserDict,
    target_language: str,
    translate_title: bool,
    translate_content: bool,
    translate_engine: TranslatorEngine,
    summary: bool,
    summary_detail: float,
    summary_engine: TranslatorEngine,
    max_posts: int = 20,
    translation_display: int = 0,
    quality: bool = False,
    fetch_article: bool = False,
) -> dict:
    logging.info(
        "Call task translate_feed: %s(%s items)", target_language, len(feed.entries)
    )
    translated_feed = feed
    total_tokens = 0
    translated_characters = 0
    need_cache_objs = {}
    source_language = "auto"

    try:
        for entry in translated_feed.entries[:max_posts]:
            title = entry.get("title")
            source_language = text_handler.detect_language(entry)

            # Translate title
            if title and translate_engine and translate_title:
                cached = Translated_Content.is_translated(
                    title, target_language
                )  # check cache db
                translated_title = ""
                if not cached:
                    max_retries = 3
                    for attempt in range(max_retries):
                        results = translate_engine.translate(
                            title,
                            target_language=target_language,
                            source_language=source_language,
                            text_type="title",
                        )
                        translated_title = results.get("text", "")
                        if translated_title:
                            break
                        logging.warning(
                            f"Empty translation for title, retrying (attempt {attempt + 1}/{max_retries})"
                        )

                    if not translated_title:
                        translated_title = (
                            title  # Fallback to original title if all retries fail
                        )

                    total_tokens += results.get("tokens", 0)
                    translated_characters += len(title)
                    if title and translated_title:
                        logging.info("[Title] Will cache:%s", translated_title)
                        hash128 = cityhash.CityHash128(f"{title}{target_language}")
                        need_cache_objs[hash128] = Translated_Content(
                            hash=str(hash128),
                            original_content=title,
                            translated_language=target_language,
                            translated_content=translated_title,
                            tokens=results.get("tokens", 0),
                            characters=results.get("characters", 0),
                        )
                else:
                    logging.info("[Title] Use db cache:%s", cached["text"])
                    translated_title = cached["text"]

                entry["title"] = text_handler.set_translation_display(
                    original=title,
                    translation=translated_title,
                    translation_display=translation_display,
                    seprator=" || ",
                )
                bulk_save_cache(need_cache_objs)
                need_cache_objs = {}

            if fetch_article:
                try:
                    article = newspaper.article(
                        entry.get("link")
                    )  # 勿使用build，因为不支持跳转
                    entry["content"] = [{"value": mistune.html(article.text)}]
                except Exception as e:
                    logging.warning("Fetch original article error:%s", e)

            # Translate content
            if translate_engine and translate_content:
                original_content = entry.get("content")
                content = (
                    original_content[0].get("value")
                    if original_content
                    else entry.get("summary")
                )

                if content:
                    max_retries = 3
                    for attempt in range(max_retries):
                        translated_summary, tokens, characters, need_cache = (
                            content_translate(
                                content,
                                target_language,
                                translate_engine,
                                translate_title,
                                quality,
                                source_language,
                            )
                        )
                        if translated_summary:
                            break
                        logging.warning(
                            f"Empty translation for content, retrying (attempt {attempt + 1}/{max_retries})"
                        )

                    if not translated_summary:
                        translated_summary = (
                            content  # Fallback to original content if all retries fail
                        )

                    if quality:
                        translation = mistune.html(translated_summary)
                    else:
                        translation = translated_summary

                    total_tokens += tokens
                    translated_characters += characters

                    need_cache_objs.update(need_cache)

                    text = text_handler.set_translation_display(
                        original=content,
                        # NOTE: 将翻译得到的 Markdown 转换为 HTML
                        translation=translation,
                        translation_display=translation_display,
                        seprator="<br />---------------<br />",
                    )
                    entry["summary"] = text
                    entry["content"] = [{"value": text}]

                    bulk_save_cache(need_cache_objs)
                    need_cache_objs = {}

            if summary_engine and summary:
                if summary_engine == None:
                    logging.warning("No Summarize engine")
                    continue
                original_content = entry.get("content")
                content = (
                    original_content[0].get("value")
                    if original_content
                    else entry.get("summary")
                )

                if content:
                    max_retries = 3
                    for attempt in range(max_retries):
                        summary_text, tokens, need_cache = content_summarize(
                            content,
                            target_language=target_language,
                            detail=summary_detail,
                            engine=summary_engine,
                            minimum_chunk_size=summary_engine.max_size(),
                        )
                        if summary_text:
                            break
                        logging.warning(
                            f"Empty summary, retrying (attempt {attempt + 1}/{max_retries})"
                        )

                    if not summary_text:
                        summary_text = (
                            content  # Fallback to original content if all retries fail
                        )

                    total_tokens += tokens
                    need_cache_objs.update(need_cache)
                    html_summary = f"<br />🤖:{mistune.html(summary_text)}<br />---------------<br />"

                    entry["summary"] = summary_text
                    entry["content"] = [{"value": html_summary + content}]

                    bulk_save_cache(need_cache_objs)
                    need_cache_objs = {}

    except Exception as e:
        logging.error("translate_feed: %s", str(e))
    finally:
        bulk_save_cache(need_cache_objs)
        need_cache_objs = {}

    return {
        "feed": translated_feed,
        "tokens": total_tokens,
        "characters": translated_characters,
    }


def bulk_save_cache(need_cache_objs):
    try:
        if need_cache_objs:
            logging.info("Save caches to db")
            Translated_Content.objects.bulk_create(need_cache_objs.values())
    except IntegrityError:
        logging.warning("Save cache: A record with this hash value already exists.")
    except Exception as e:
        logging.error("Save cache: %s", str(e))
    return True


def content_translate(
    original_content: str,
    target_language: str,
    engine: TranslatorEngine,
    translate_title: str,
    quality: bool = False,
    source_language: str = "auto",
) -> tuple[str, int, int, dict]:
    """Translate content using either chunk or tag based translation.

    Returns:
        tuple: (translated_content, total_tokens, total_characters, cache_objects)
    """
    try:
        logging.info(
            "Starting content translation: mode=%s, language=%s",
            "chunk" if quality else "tag",
            target_language,
        )

        if quality:
            return chunk_translate(
                original_content=original_content,
                target_language=target_language,
                engine=engine,
                source_language=source_language,
                translate_title=translate_title,
            )
        else:
            return tag_translate(
                original_content=original_content,
                target_language=target_language,
                engine=engine,
                source_language=source_language,
            )
    except Exception as e:
        logging.error(f"Content translation failed: {str(e)}")
        return "", 0, 0, {}


def tag_translate(
    original_content: str,
    target_language: str,
    engine: TranslatorEngine,
    source_language: str = "auto",
):
    total_tokens = 0
    total_characters = 0
    need_cache_objs = {}
    soup = BeautifulSoup(original_content, "lxml")

    try:
        soup = BeautifulSoup(text_handler.unwrap_tags(soup), "lxml")

        for element in soup.find_all(string=True):
            if text_handler.should_skip(element):
                continue
            text = element.get_text()

            logging.info("[Content] Translate: %s...", text)
            cached = Translated_Content.is_translated(text, target_language)

            if not cached:
                results = engine.translate(
                    text,
                    target_language=target_language,
                    source_language=source_language,
                    text_type="content",
                )
                total_tokens += results.get("tokens", 0)
                total_characters += len(text)

                if results["text"]:
                    logging.info("[Content] Will cache:%s", results["text"])
                    hash128 = cityhash.CityHash128(f"{text}{target_language}")
                    need_cache_objs[hash128] = Translated_Content(
                        hash=str(hash128),
                        original_content=text,
                        translated_language=target_language,
                        translated_content=results["text"],
                        tokens=results.get("tokens", 0),
                        characters=results.get("characters", 0),
                    )

                element.string.replace_with(results.get("text", text))
            else:
                logging.info("[Content] Use db cache:%s", text)
                element.string.replace_with(cached.get("text"))
    except Exception as e:
        logging.error(f"content_translate: {str(e)}")

    return str(soup), total_tokens, total_characters, need_cache_objs


def chunk_translate(
    original_content: str,
    target_language: str,
    engine: TranslatorEngine,
    translate_title: str,
    source_language: str = "auto",
):
    logging.info(
        "Call chunk_translate: %s(%s items)", target_language, len(original_content)
    )
    split_chunks: dict = text_handler.content_split(original_content)
    grouped_chunks: list = text_handler.group_chunks(
        split_chunks=split_chunks,
        max_size=engine.max_size(),
        group_by="tokens",
    )
    translated_content = []
    total_tokens = 0
    total_characters = 0
    need_cache_objs: dict = {}
    for chunk in grouped_chunks:
        if not chunk:
            continue
        logging.info("Translate chunk: %s", chunk)
        cached = Translated_Content.is_translated(chunk, target_language)
        if not cached:
            results = engine.translate(
                chunk,
                target_language=target_language,
                text_type="content",
                source_language=source_language,
                translate_title=translate_title,
            )
            results_content = re.sub("^##\s+", "", results["text"])
            translated_content.append(results_content if results else chunk)
            total_tokens += results.get("tokens", 0)
            total_characters += len(chunk)

            if chunk and results["text"]:
                logging.info("Save to cache:%s", results_content)
                hash128 = cityhash.CityHash128(f"{chunk}{target_language}")
                need_cache_objs[hash128] = Translated_Content(
                    hash=str(hash128),
                    original_content=chunk,
                    translated_language=target_language,
                    translated_content=results_content,
                    tokens=results.get("tokens", 0),
                    characters=results.get("characters", 0),
                )
        else:
            translated_content.append(cached["text"])
    return (
        str("\n\n".join(translated_content)),
        total_tokens,
        total_characters,
        need_cache_objs,
    )


def content_summarize(
    original_content: str,
    target_language: str,
    engine: TranslatorEngine,
    detail: float = 0.0,
    minimum_chunk_size: Optional[int] = 500,
    chunk_delimiter: str = ".",
    summarize_recursively=True,
):
    # check detail is set correctly
    assert 0 <= detail <= 1

    total_tokens = 0
    need_cache_objs = {}
    final_summary = ""
    try:
        text = text_handler.clean_content(original_content)
        logging.info("[Summarize]: %s...", text)
        cached = Translated_Content.is_translated(
            f"Summary_{original_content}", target_language
        )

        if not cached:
            # interpolate the number of chunks based to get specified level of detail
            max_chunks = len(
                text_handler.chunk_on_delimiter(
                    text, minimum_chunk_size, chunk_delimiter
                )
            )
            min_chunks = 1
            num_chunks = int(min_chunks + detail * (max_chunks - min_chunks))

            # adjust chunk_size based on interpolated number of chunks
            document_length = len(text_handler.tokenize(text))
            chunk_size = max(minimum_chunk_size, document_length // num_chunks)
            text_chunks = text_handler.chunk_on_delimiter(
                text, chunk_size, chunk_delimiter
            )

            logging.info(
                "Splitting the text into %d chunks to be summarized.", len(text_chunks)
            )
            # logging.info(f"Chunk lengths are {[len(text_handler.tokenize(x)) for x in text_chunks]}")

            accumulated_summaries = []
            for chunk in text_chunks:
                if summarize_recursively and accumulated_summaries:
                    # Creating a structured prompt for recursive summarization
                    accumulated_summaries_string = "\n\n".join(accumulated_summaries)
                    user_message_content = f"Previous summaries:\n\n{accumulated_summaries_string}\n\nText to summarize next:\n\n{chunk}"
                else:
                    # Directly passing the chunk for summarization without recursive context
                    user_message_content = chunk

                # Assuming this function gets the completion and works as expected
                response = engine.summarize(user_message_content, target_language)
                accumulated_summaries.append(response.get("text"))
                total_tokens += response.get("tokens", 0)

            # Compile final summary from partial summaries
            final_summary = "<br/>".join(accumulated_summaries)

            hash128 = cityhash.CityHash128(
                f"Summary_{original_content}{target_language}"
            )
            logging.info("[Summary] Will cache:%s", final_summary)
            need_cache_objs[hash128] = Translated_Content(
                hash=str(hash128),
                original_content=f"Summary_{original_content}",
                translated_language=target_language,
                translated_content=final_summary,
                tokens=total_tokens,
                characters=0,
            )
        else:
            final_summary = cached.get("text")
            logging.info("[Summary] Use db cache:%s", final_summary)
    except Exception as e:
        logging.error(f"content_summarize: {str(e)}")

    return final_summary, total_tokens, need_cache_objs
