"""Natural-language command parser for Discord server administration:
create/delete/list channels and roles, assign/remove a role on a member.
No LLM, regex only — same approach as tasks_parser.py/lists_parser.py.

Discord-only on purpose: these need a live discord.Guild to do anything, so
unlike tasks/lists this never routes through sunny_code.components.assistant
— discord_bot.py checks this parser directly, before falling through to the
shared cross-interface router. See sunny-vault/docs/architecture/discord-bot.md.
"""

import re
from typing import Dict, Optional, Tuple

_MENTION = r'<@!?(\d+)>'
_NAME = r"[\w][\w '-]*"  # letters/digits/underscore/space/apostrophe/hyphen, must start with word char


class ServerAdminParser:
    """Parse server-admin commands. Returns (action, data) or None if nothing matched.
    Actions: create_channel, delete_channel, list_channels,
             create_role, delete_role, list_roles, assign_role, remove_role."""

    LIST_CHANNELS = re.compile(r'^(?:list|show)\s+channels\??$', re.IGNORECASE)
    CREATE_CHANNEL = re.compile(
        r'^(?:create|add|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:text\s+)?channel\s+'
        r'(?:called\s+|named\s+)?#?([\w-]+)$', re.IGNORECASE
    )
    DELETE_CHANNEL = re.compile(
        r'^(?:delete|remove)\s+(?:the\s+)?channel\s+(?:called\s+|named\s+)?#?([\w-]+)$', re.IGNORECASE
    )

    LIST_ROLES = re.compile(r'^(?:list|show)\s+roles\??$', re.IGNORECASE)
    CREATE_ROLE = re.compile(
        rf'^(?:create|add|make)\s+(?:a\s+|an\s+)?(?:new\s+)?role\s+(?:called\s+|named\s+)?@?({_NAME})$',
        re.IGNORECASE,
    )
    DELETE_ROLE = re.compile(
        rf'^(?:delete|remove)\s+(?:the\s+)?role\s+(?:called\s+|named\s+)?@?({_NAME})$', re.IGNORECASE
    )

    ASSIGN_ROLE_A = re.compile(rf'^(?:give|add)\s+{_MENTION}\s+(?:the\s+)?({_NAME}?)\s+role$', re.IGNORECASE)
    ASSIGN_ROLE_B = re.compile(rf'^(?:give|add)\s+(?:the\s+)?({_NAME}?)\s+role\s+to\s+{_MENTION}$', re.IGNORECASE)
    REMOVE_ROLE_A = re.compile(rf'^remove\s+{_MENTION}\s+from\s+(?:the\s+)?({_NAME}?)\s+role$', re.IGNORECASE)
    REMOVE_ROLE_B = re.compile(rf'^remove\s+(?:the\s+)?({_NAME}?)\s+role\s+from\s+{_MENTION}$', re.IGNORECASE)

    @classmethod
    def parse(cls, text: str) -> Optional[Tuple[str, Dict]]:
        stripped = text.strip()

        if cls.LIST_CHANNELS.match(stripped):
            return "list_channels", {}
        match = cls.CREATE_CHANNEL.match(stripped)
        if match:
            return "create_channel", {"name": match.group(1)}
        match = cls.DELETE_CHANNEL.match(stripped)
        if match:
            return "delete_channel", {"name": match.group(1)}

        if cls.LIST_ROLES.match(stripped):
            return "list_roles", {}
        match = cls.CREATE_ROLE.match(stripped)
        if match:
            return "create_role", {"name": match.group(1).strip()}
        match = cls.DELETE_ROLE.match(stripped)
        if match:
            return "delete_role", {"name": match.group(1).strip()}

        match = cls.ASSIGN_ROLE_A.match(stripped)
        if match:
            return "assign_role", {"user_id": int(match.group(1)), "role_name": match.group(2).strip()}
        match = cls.ASSIGN_ROLE_B.match(stripped)
        if match:
            return "assign_role", {"role_name": match.group(1).strip(), "user_id": int(match.group(2))}

        match = cls.REMOVE_ROLE_A.match(stripped)
        if match:
            return "remove_role", {"user_id": int(match.group(1)), "role_name": match.group(2).strip()}
        match = cls.REMOVE_ROLE_B.match(stripped)
        if match:
            return "remove_role", {"role_name": match.group(1).strip(), "user_id": int(match.group(2))}

        return None
