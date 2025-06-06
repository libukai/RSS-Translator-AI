import logging
import re
from typing import List, Optional, Tuple

import html2text
import tiktoken
from bs4 import Comment
from langdetect import detect
from markdownify import markdownify


def detect_language(entry):
    title = entry.get("title")
    original_content = entry.get("content")
    content = (
        original_content[0].get("value") if original_content else entry.get("summary")
    )
    text = f"{title} {content}"
    source_language = "auto"
    try:
        source_language = detect(text)
    except Exception as e:
        logging.warning("Cannot detect source language:%s,%s", e, text)

    return source_language


def clean_content(content: str) -> str:
    """convert html to markdown without useless tags"""
    h = html2text.HTML2Text()
    h.decode_errors = "ignore"
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_tables = True
    h.ignore_emphasis = True
    h.single_line_break = True
    h.no_wrap_links = True
    h.mark_code = True
    h.unicode_snob = True
    h.body_width = 0
    h.drop_white_space = True
    h.ignore_mailto_links = True

    # content = h.handle(h.handle(content)) #remove all \n
    content = h.handle(content)
    content = re.sub(r"\n\s*\n", "\n", content)
    return content


# Thanks to https://github.com/openai/openai-cookbook/blob/main/examples/Summarizing_with_controllable_detail.ipynb
def tokenize(text: str) -> List[str]:
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return encoding.encode(text)


"""
This function combines text chunks into larger blocks without exceeding a specified token count. 
It returns the combined text blocks, their original indices, and the count of chunks dropped due to overflow.
"""


def combine_chunks_with_no_minimum(
    chunks: List[str],
    max_tokens: int,
    chunk_delimiter="\n",
    header: Optional[str] = None,
    add_ellipsis_for_overflow=False,
) -> Tuple[List[str], List[int]]:
    """
    This function combines text chunks into larger blocks without exceeding a specified token count.
    It returns the combined text blocks, their original indices, and the count of chunks dropped due to overflow.
    """
    dropped_chunk_count = 0
    output = []  # list to hold the final combined chunks
    output_indices = []  # list to hold the indices of the final combined chunks
    candidate = (
        [] if header is None else [header]
    )  # list to hold the current combined chunk candidate
    candidate_indices = []
    for chunk_i, chunk in enumerate(chunks):
        chunk_with_header = [chunk] if header is None else [header, chunk]
        if len(tokenize(chunk_delimiter.join(chunk_with_header))) > max_tokens:
            logging.warning("chunk overflow")
            if (
                add_ellipsis_for_overflow
                and len(tokenize(chunk_delimiter.join(candidate + ["..."])))
                <= max_tokens
            ):
                candidate.append("...")
                dropped_chunk_count += 1
            continue  # this case would break downstream assumptions
        # estimate token count with the current chunk added
        extended_candidate_token_count = len(
            tokenize(chunk_delimiter.join(candidate + [chunk]))
        )
        # If the token count exceeds max_tokens, add the current candidate to output and start a new candidate
        if extended_candidate_token_count > max_tokens:
            output.append(chunk_delimiter.join(candidate))
            output_indices.append(candidate_indices)
            candidate = chunk_with_header  # re-initialize candidate
            candidate_indices = [chunk_i]
        # otherwise keep extending the candidate
        else:
            candidate.append(chunk)
            candidate_indices.append(chunk_i)
    # add the remaining candidate to output if it's not empty
    if (header is not None and len(candidate) > 1) or (
        header is None and len(candidate) > 0
    ):
        output.append(chunk_delimiter.join(candidate))
        output_indices.append(candidate_indices)
    return output, output_indices, dropped_chunk_count


def chunk_on_delimiter(
    input_string: str, max_tokens: int, delimiter: str = " "
) -> List[str]:
    """
    This function chunks a text into smaller pieces based on a maximum token count and a delimiter.
    """
    chunks = input_string.split(delimiter)
    combined_chunks, _, dropped_chunk_count = combine_chunks_with_no_minimum(
        chunks, max_tokens, chunk_delimiter=delimiter, add_ellipsis_for_overflow=True
    )
    if dropped_chunk_count > 0:
        logging.warning("%d chunks were dropped due to overflow", dropped_chunk_count)
    combined_chunks = [f"{chunk}{delimiter}" for chunk in combined_chunks]
    return combined_chunks


def content_split(content: str) -> dict:
    """
    Split content into chunks, separated by one or more newlines.
    # https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
    #encoding = tiktoken.get_encoding("cl100k_base")
    """
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    try:
        markdown = markdownify(
            content, keep_inline_images_in=["td"], heading_style="ATX"
        )
        chunks = re.split("\n+", markdown)
        tokens = []
        characters = []
        for chunk in chunks:
            tokens.append(len(encoding.encode(chunk)))
            characters.append(len(chunk))
    except Exception as e:
        logging.error(f"content_split: {str(e)}")
        chunks = [content]
        tokens = [len(encoding.encode(content))]
        characters = [len(content)]
    return {"chunks": chunks, "tokens": tokens, "characters": characters}


def group_chunks(
    split_chunks: dict, max_size: int, group_by: str
) -> list:  # group_by: 'tokens' or 'characters'
    """Group very short chunks, to form approximately page long chunks."""
    chunks = split_chunks["chunks"]
    values = split_chunks[group_by]
    grouped_chunks = []
    current_chunk = ""
    current_value = 0
    # NOTE: 将 chunk 进行拼接，按照 max_size 的一半长度来吐给 AI 进行翻译
    try:
        for chunk, value in zip(chunks, values):
            if (current_value + value) > (max_size / 2):
                # If adding the current chunk exceeds 1/2 of max_size, add the current_chunk to grouped_chunks
                grouped_chunks.append(current_chunk.strip())
                # Start a new current_chunk with the current chunk
                current_chunk = chunk
                current_value = value
            else:
                # If adding the current chunk does not exceed 1/2 of max_size, add it to current_chunk
                if chunk.startswith("|"):
                    current_chunk += "\n" + chunk
                else:
                    current_chunk += "\n\n" + chunk
                current_value += value

        # Add the last current_chunk to grouped_chunks
        if current_chunk:
            grouped_chunks.append(current_chunk.strip())
    except Exception as e:
        logging.error(f"group_chunks: {str(e)}")
        grouped_chunks = chunks

    return grouped_chunks


def should_skip(element):
    skip_tags = [
        "pre",
        "code",
        "script",
        "style",
        "head",
        "title",
        "meta",
        "abbr",
        "address",
        "samp",
        "kbd",
        "bdo",
        "cite",
        "dfn",
        "iframe",
    ]
    if isinstance(element, Comment):
        return True
    if element.find_parents(skip_tags):
        return True

    text = element.get_text(strip=True)
    if not text:
        return True

    # 使用正则表达式来检查元素是否为数字、URL、电子邮件或包含特定符号
    skip_patterns = [
        r"^http",  # URL
        r"^[^@]+@[^@]+\.[^@]+$",  # 电子邮件
        r"^[\d\W]+$",  # 纯数字或者数字和符号的组合
    ]

    for pattern in skip_patterns:
        if re.match(pattern, text):
            return True

    return False


def unwrap_tags(soup) -> str:
    tags_to_unwrap = [
        "i",
        "a",
        "strong",
        "b",
        "em",
        "span",
        "sup",
        "sub",
        "mark",
        "del",
        "ins",
        "u",
        "s",
        "small",
    ]
    for tag_name in tags_to_unwrap:
        for tag in soup.find_all(tag_name):
            tag.unwrap()
    return str(soup)


def set_translation_display(
    original: str, translation: str, translation_display: int, seprator: str = " || "
) -> str:
    if translation_display == 0:  #'Only Translation'
        return translation
    elif translation_display == 1:  #'Translation || Original'
        return f"{translation}{seprator}{original}"
    elif translation_display == 2:  #'Original || Translation'
        return f"{original}{seprator}{translation}"
    else:
        return ""
