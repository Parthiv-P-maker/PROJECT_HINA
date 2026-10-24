# Tool registry

Every command Hina understands is **one** `@tool(...)`-decorated function in this
package. The registry (`registry.py`) generates everything else from it:

| Generated | Used by |
|---|---|
| free-text -> normalized command (`normalize`) | `parser.normalize_command` |
| Ollama tool schema (`ai_schemas`) and execution (`call_ai`) | `core/ai_engine.py` (`TOOLS`, `_call_tool`) |
| known-command check (`is_known_command`, `known_prefixes`) | `core/command_router.py` |
| AI string-mapping prompt list (`prompt_commands`) | `core/ai_engine.py` |
| dispatch (`dispatch`) | `core/dispatcher.py` |
| permission tier | `permissions.TIERS` / `tier_of` |

## Adding a command

```python
# tools/system.py (or any module imported in tools/__init__.py)
@tool("uptime", "Tell the user how long the computer has been on.",
      command="uptime", exact_triggers=("uptime", "how long has the pc been on"), ai=True)
def uptime():
    return actions.uptime()
```

Handlers take no argument, or a `ToolContext` (`ctx.arg` = text after the command
prefix, `ctx.via_ai`, `ctx.run(target, fn)` to run under the tool's permission tier,
`ctx.output_var/output_label/app` GUI hooks). They return a string or a `DispatchResult`.
Call `actions.x(...)` through the module (not `from actions import x`) so tests can patch it.

Options: `params={"name": Param("...")}` (a tool with params takes an argument and its
`command` is a prefix such as `"open "`), `tier=SAFE|CONFIRM|BLOCKED`, `ai=True` to expose it
to the model, `aliases`, `triggers` (substrings), `exact_triggers`, `starts`, or a custom
`parse(text)` for the parser, `priority` (parse order, lower first), `router=False` /
`prompt=False` to hide it from the router / AI prompt.

`tests/test_registry.py` fails if a registered tool is missing from the schema, router or
dispatcher. Parse order matters (first match wins): see the `priority` values in the modules.
