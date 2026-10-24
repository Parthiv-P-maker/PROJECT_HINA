"""Web search."""

import actions
from tools.registry import Param, tool


def _parse_chatgpt(text):
    if "search" in text and "in chatgpt" in text:
        query = (
            text.replace("search", "")
            .replace("in chatgpt", "")
            .replace("about", "")
            .strip()
        )
        return "search chatgpt " + query
    if text.startswith("ask chatgpt about "):
        return "search chatgpt " + text.replace("ask chatgpt about ", "").strip()
    return None


def _parse_google(text):
    if text.startswith("search "):
        return "search google " + text.replace("search ", "").strip()
    if text.startswith("google "):
        return "search google " + text.replace("google ", "").strip()
    return None


@tool("search_chatgpt", "Open ChatGPT in the browser with a query.",
      {"query": Param("Query to ask ChatGPT")},
      command="search chatgpt ", parse=_parse_chatgpt, ai=True, prompt=False, priority=70)
def search_chatgpt(ctx):
    return actions.search_chatgpt(ctx.arg.strip())


@tool("search_google", "Search Google for a query in the default browser.",
      {"query": Param("Search query")},
      command="search google ", parse=_parse_google, ai=True, prompt=False, priority=71)
def search_google(ctx):
    return actions.search_google(ctx.arg.strip())
