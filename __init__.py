import logging

import dataset

from telepot import glance, message_identifier
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

from skybeard.beards import (BeardChatHandler,
                             ThatsNotMineException,
                             BeardDBTable)
from skybeard.decorators import onerror

from . import config

logger = logging.getLogger(__name__)


def get_full_name(chat_member):
    try:
        if chat_member['last_name']:
            name = chat_member['first_name']+" "+chat_member['last_name']
        else:
            name = chat_member['first_name']
    except KeyError:
        name = chat_member['first_name']

    return name


# async def check_for_messages(to_user_id, chat_id):
#     """Find any messages currently waiting for a user."""
#     with dataset.connect(config.db_path) as db:
#         table = db['messages']
#         return table.find(to_user_id=to_user_id, chat_id=chat_id)


# async def insert_message(to_user_id, message):
#     """Inserts a message to be forwarded into the database."""
#     event = dict(
#         to_user_id=to_user_id,
#         chat_id=message['chat']['id'],
#         from_chat_id=message['chat']['id'],
#         message_id=message['message_id'],
#         from_user_name=get_full_name(message['from'])
#     )

#     with dataset.connect(config.db_path) as db:
#         table = db['messages']
#         return table.insert(event)


# def is_chat_member_recorded(msg):
#     with dataset.connect(config.db_path) as db:
#         table = db.get_table('chats', 'database_id')
#         try:
#             return table.find_one(**msg['from'], chat_id=msg['chat']['id'])
#         except AttributeError:
#             return


# async def get_chat_member(chat_id, user_id):
#     with dataset.connect(config.db_path) as db:
#         table = db.get_table('chats', 'database_id')
#         x = table.find_one(chat_id=chat_id, id=user_id)
#         assert x, "Failed to find entry for (chat_id, id) = ({}, {})".format(chat_id, user_id)
#         return x


# async def get_chat_members(chat_id):
#     with dataset.connect(config.db_path) as db:
#         table = db.get_table('chats', 'database_id')
#         results_found = table.find(chat_id=chat_id)
#         results_to_return = []
#         for result in results_found:
#             del result['chat_id']
#             del result['database_id']
#             results_to_return.append(result)

#         return results_to_return


# async def insert_chat_member(chat_id, from_user):
#     with dataset.connect(config.db_path) as db:
#         table = db.get_table('chats', 'database_id')
#         return table.insert(dict(**from_user, chat_id=chat_id))


def format_db_entry(entry):
    return str(entry['message'])


async def delete_message(entry):
    """Deletes message from database"""
    with dataset.connect(config.db_path) as db:
        table = db['messages']
        table.delete(**entry)


class LetThemKnowBeard(BeardChatHandler):

    __commands__ = [
        ("letthemknow", 'let_them_know',
         "Schedule a message for someone to see later."),
        # (lambda c, m: not(is_chat_member_recorded(m)), 'record_new_chat_member',
         # None)
    ]

    _timeout = 300

    __userhelp__ = "This beard schedules messages for others to see later."

    def __init__(self, *args, **kwargs):
        "docstring"
        super().__init__(*args, **kwargs)
        self.recording_message = False
        self.message_to_record = None
        self.message_to_request_user_id = None
        self.chat_member_table = BeardDBTable(self, 'chats',
                                              primary_id='database_id')
        self.messages_table = BeardDBTable(self, 'messages')

        self.register_command(self.is_chat_member_not_recorded,
                              self.record_new_chat_member)

    async def is_chat_member_not_recorded(self, _, msg):
        with self.chat_member_table as table:
            try:
                return not table.find_one(**msg['from'])
            except AttributeError:
                return

    async def record_new_chat_member(self, msg):
        self.logger.debug(
            "I've not seen you before! Recording you for LetThemKnowBeard.")
        with self.chat_member_table as table:
            return table.insert(dict(**msg['from']))

    async def check_for_messages(self, to_user_id):
        """Find any messages currently waiting for a user."""
        with self.messages_table as table:
            return table.find(to_user_id=to_user_id)

    async def delete_message(self, entry):
        """Deletes message from database"""
        with self.messages_table as table:
            table.delete(**entry)

    async def on_chat_message(self, msg):
        # Check if anyone needs to be told a message
        pregnant_msgs = await self.check_for_messages(msg['from']['id'])
        for pregnant_msg in pregnant_msgs:
            await self.sender.sendMessage(
                "By the way, {} wanted me to let you know:".format(
                    pregnant_msg['from_user_name']))
            await self.sender.forwardMessage(
                from_chat_id=pregnant_msg['from_chat_id'],
                message_id=pregnant_msg['message_id']
            )
            await self.delete_message(pregnant_msg)

        await super().on_chat_message(msg)

    async def get_chat_member(self, user_id):
        # with dataset.connect(config.db_path) as db:
            # table = db.get_table('chats', 'database_id')
        with self.chat_member_table as table:
            x = table.find_one(id=user_id)
            assert x,\
                "Failed to find entry for id = ({})".format(
                    user_id)
            return x

    async def get_chat_members(self):
    # with dataset.connect(config.db_path) as db:
        with self.chat_member_table as table:
            results_found = table.all()
            results_to_return = []
            for result in results_found:
                del result['database_id']
                results_to_return.append(result)

            return results_to_return

    async def make_keyboard(self):
        chat_members = await self.get_chat_members()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text=get_full_name(x),
                callback_data=self.serialize(x['id']))]
             for x in chat_members])

        return keyboard

    async def on_callback_query(self, msg):
        query_id, from_id, query_data = glance(msg, flavor='callback_query')
        try:
            data = self.deserialize(query_data)
        except ThatsNotMineException:
            return

        self.logger.debug("Callback data recieved: {}".format(data))
        # TODO answercallbackquery

        if self.recording_message:
            await self.finish_let_them_know(msg)

    @onerror
    async def finish_let_them_know(self, msg):
            query_id, from_id, query_data = glance(msg, flavor='callback_query')
            data = self.deserialize(query_data)
            name_of_message_recipient = get_full_name(
                await self.get_chat_member(data))
            await self.bot.editMessageText(
                message_identifier(self.message_to_request_user_id),
                self.message_to_request_user_id['text'])
            await self.sender.sendMessage(
                "OK, recording a message for {}.\n\nWhat's the message?".format(
                    name_of_message_recipient))
            self.message_to_record = await self.listener.wait()
            await self.insert_message(
                data,
                self.message_to_record,
            )
            await self.sender.sendMessage("I'll let them know.")

            self.recording_message = False
            self.message_to_record = None

    @onerror
    async def let_them_know(self, msg):
        if self.recording_message:
            await self.sender.sendMessage("Already recording message!")
            return

        self.message_to_request_user_id = await self.sender.sendMessage(
            "Who's the message for?",
            reply_markup=await self.make_keyboard())
        self.recording_message = True

    async def insert_message(self, to_user_id, message):
        """Inserts a message to be forwarded into the database."""
        event = dict(
            to_user_id=to_user_id,
            from_chat_id=message['chat']['id'],
            message_id=message['message_id'],
            from_user_name=get_full_name(message['from'])
        )

        with self.messages_table as table:
            return table.insert(event)
