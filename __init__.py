import logging
import dice
import re

from skybeard.beards import BeardChatHandler
from skybeard import utils
from skybeard.decorators import onerror

logger = logging.getLogger(__name__)

import dataset

DB = "sqlite:///letthemknowbeard.db"


async def check_for_messages(to_user_id, chat_id):
    """Find any messages currently waiting for a user."""
    with dataset.connect(DB) as db:
        table = db['messages']
        return table.find(to_user_id=to_user_id, chat_id=chat_id)


async def insert_message(to_user_id, message):
    # TODO insert full message object so that this function can do the heavy lifting
    """Find any messages currently waiting for a user."""
    chat_id = message['chat']['id']
    message_text = message['text']
    try:
        from_user_name = message['from']['first_name']+" "+message['from']['last_name']
    except KeyError:
        try:
            from_user_name = message['from']['first_name']
        except KeyError:
            from_user_name = message['from']['username']

    with dataset.connect(DB) as db:
        table = db['messages']
        return table.insert(
            dict(to_user_id=to_user_id,
                 from_user_name=from_user_name,
                 chat_id=chat_id,
                 message=message_text))


def format_db_entry(entry):
    return str(entry['message'])


async def delete_message(entry):
    """Deletes message from database"""
    with dataset.connect(DB) as db:
        table = db['messages']
        table.delete(**entry)


class LetThemKnowBeard(BeardChatHandler):

    __commands__ = [
        ("letthemknow", 'let_them_know', "TODO"),
    ]

    _timeout = 300

    __userhelp__ = "TODO"

    @onerror
    async def on_chat_message(self, msg):
        # Check if anyone needs to be told a message
        pregnant_msgs = await check_for_messages(
            msg['from']['id'], self.chat_id)
        for pregnant_msg in pregnant_msgs:
            await self.sender.sendMessage(
                "By the way, {} wanted me to let you know:\n\n{}".format(
                    pregnant_msg['from_user_name'],
                    format_db_entry(pregnant_msg)))
            await delete_message(pregnant_msg)

        await super().on_chat_message(msg)

    @onerror
    async def let_them_know(self, msg):
        await self.sender.sendMessage(
            "What's the message for them? (I'll ask who for later)")
        message_resp = await self.listener.wait()
        await self.sender.sendMessage(
            "What's the user id of the person whom it's for?")
        user_id_resp = await self.listener.wait()

        await insert_message(
            user_id_resp['text'],
            message_resp
        )

        await self.sender.sendMessage(
            "Message recorded.")
