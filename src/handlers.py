# Marakulin Andrey https://github.com/Annndruha
# 2023

import logging
import functools
import threading
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from telegram.constants import ParseMode

from gql.transport.exceptions import TransportQueryError, TransportAlreadyConnected, TransportError

from src.settings import Settings
from src.issue_message import TgIssueMessage
from src.github_api import Github
from src.answers import Answers

ans = Answers()
settings = Settings()
github = Github(settings)


def error_handler(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            await func(update, context)
        except TransportAlreadyConnected as err:
            logging.warning(f'TransportAlreadyConnected: {err.args}')
            await context.bot.answer_callback_query(callback_query_id=update.callback_query.id,
                                                    text='The previous request not done yet.\nPlease wait...')
        except TransportQueryError as err:
            logging.warning(f'Failed to open Issue: {err}')
            match err.errors[0]['type']:
                case 'NOT_FOUND':
                    text = 'Issue not found'
                    await update.callback_query.edit_message_text(text=text)
                case 'FORBIDDEN':
                    text = 'Issue disabled for this repo'
                case _:
                    text = err.errors[0]['message']
            await context.bot.answer_callback_query(callback_query_id=update.callback_query.id, text=text)
        except TransportError as err:
            logging.warning(f'TransportError: {err.args}')
            await context.bot.answer_callback_query(callback_query_id=update.callback_query.id, text=err.args)
        except Exception as err:
            logging.error(err)
            traceback.print_tb(err.__traceback__)
    return wrapper


def log_formatter(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query is None:
            logging.info(f'[{update.message.from_user.id} {update.message.from_user.full_name}] '
                         f'[{func.__name__}]: {repr(update.message.text)}')
        else:
            logging.info(f'[{update.callback_query.from_user.id} {update.callback_query.from_user.full_name}] '
                         f'[{update.callback_query.message.id}] [{func.__name__}] '
                         f'callback_data: {update.callback_query.data}')
        await func(update, context)

    return wrapper


@error_handler
@log_formatter
async def handler_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.message.chat_id,
                                   message_thread_id=update.message.message_thread_id,
                                   text=ans.start.format(settings.GH_ORGANIZATION_NICKNAME),
                                   disable_web_page_preview=True,
                                   parse_mode=ParseMode('HTML'))


@error_handler
@log_formatter
async def handler_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.message.chat_id,
                                   message_thread_id=update.message.message_thread_id,
                                   text=ans.help.format(settings.BOT_NICKNAME),
                                   disable_web_page_preview=True,
                                   parse_mode=ParseMode('HTML'))


@error_handler
@log_formatter
async def handler_md_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.message.chat_id,
                                   message_thread_id=update.message.message_thread_id,
                                   text=ans.markdown_guide_tg,
                                   disable_web_page_preview=True,
                                   parse_mode=ParseMode('HTML'))
    await context.bot.send_message(chat_id=update.message.chat_id,
                                   message_thread_id=update.message.message_thread_id,
                                   text=ans.markdown_guide_md,
                                   disable_web_page_preview=True,
                                   )


@error_handler
@log_formatter
async def handler_button(update: Update, context: CallbackContext) -> None:
    callback_data = update.callback_query.data
    action = callback_data.split('_', 1)[0]
    text = update.callback_query.message.text_html

    match action:
        case 'setup':
            issue_id = __search_issue_id_in_keyboard(update)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('↩️', callback_data=f'quite_{issue_id}'),
                                              InlineKeyboardButton('🗄 ', callback_data=f'repos_start'),
                                              InlineKeyboardButton('👤', callback_data=f'members_start'),
                                              InlineKeyboardButton('❌', callback_data=f'close_{issue_id}')]])
        case 'quite':
            if update.callback_query.data == 'quite_start':
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ Select repo to create',
                                                                       callback_data='repos_start')]])
            else:
                issue_id = __search_issue_id_in_keyboard(update)
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('Setup', callback_data=f'setup_{issue_id}')]])
        case 'close':
            keyboard, text = __close_issue(update)
        case 'reopen':
            keyboard, text = __reopen_issue(update)
        case 'members':
            keyboard = __keyboard_members(update)
        case 'repos':
            keyboard = __keyboard_repos(update)
        case 'repo':
            keyboard, text = __create_issue(update)
        case 'assign':
            keyboard, text = __set_assign(update)
        case _:
            keyboard, text = None, 'Probably bot updated, issue can\'t be change.'
            logging.error('Old keyboard callback')

    await update.callback_query.edit_message_text(text=text,
                                                  reply_markup=keyboard,
                                                  disable_web_page_preview=True,
                                                  parse_mode=ParseMode('HTML'))


@error_handler
@log_formatter
async def handler_message(update: Update, context: CallbackContext) -> None:
    text_html = update.message.text_html.replace(settings.BOT_NICKNAME, '').strip()

    if len(text_html) == 0:
        await context.bot.send_message(chat_id=update.message.chat_id,
                                       message_thread_id=update.message.message_thread_id,
                                       text=ans.no_title)
        return

    imessage = TgIssueMessage()
    imessage.from_user(text_html)
    text = imessage.get_text()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ Select repo to create', callback_data='repos_start')]])
    await context.bot.send_message(chat_id=update.message.chat_id,
                                   message_thread_id=update.message.message_thread_id,
                                   text=text,
                                   reply_markup=keyboard,
                                   disable_web_page_preview=True,
                                   parse_mode=ParseMode('HTML'))


def __keyboard_repos(update):
    repos_info = github.get_repos(update.callback_query.data)
    issue_id = __search_issue_id_in_keyboard(update)

    buttons = []
    for repo in repos_info['edges']:
        buttons.append([InlineKeyboardButton(repo['node']['name'], callback_data='repo_' + repo['node']['id'])])

    buttons.append([])
    if repos_info['pageInfo']['hasPreviousPage']:
        cb_data = f'''repos_before_{repos_info['pageInfo']['startCursor']}'''
        buttons[-1].append(InlineKeyboardButton('⬅️', callback_data=cb_data))

    if issue_id is not None:
        buttons[-1].append(InlineKeyboardButton('↩️ Back', callback_data=f'quite_{issue_id}'))
    else:
        buttons[-1].append(InlineKeyboardButton('↩️ Back', callback_data=f'quite_start'))

    if repos_info['pageInfo']['hasNextPage']:
        cb_data = f'''repos_after_{repos_info['pageInfo']['endCursor']}'''
        buttons[-1].append(InlineKeyboardButton('➡️', callback_data=cb_data))

    return InlineKeyboardMarkup(buttons)


def __keyboard_members(update):
    members = github.get_members(update.callback_query.data)
    issue_id = __search_issue_id_in_keyboard(update)

    buttons = []
    for member in members['edges']:
        buttons.append([InlineKeyboardButton(member['node']['login'],
                                             callback_data='assign_' + member['node']['id'])])

    buttons.append([])
    if members['pageInfo']['hasPreviousPage']:
        cb_data = f'''members_before_{members['pageInfo']['startCursor']}'''
        buttons[-1].append(InlineKeyboardButton('⬅️', callback_data=cb_data))

    buttons[-1].append(InlineKeyboardButton('↩️ Back', callback_data=f'quite_{issue_id}'))

    if members['pageInfo']['hasNextPage']:
        cb_data = f'''members_after_{members['pageInfo']['endCursor']}'''
        buttons[-1].append(InlineKeyboardButton('➡️', callback_data=cb_data))

    return InlineKeyboardMarkup(buttons)


def __create_issue(update: Update):
    repo_id = __get_action_value(update)
    imessage = TgIssueMessage(bot_html=update.callback_query.message.text_html)

    issue_id = __search_issue_id_in_keyboard(update)
    if issue_id is not None:
        r = github.transfer_issue(repo_id, issue_id)
        imessage.set_issue_url(r['transferIssue']['issue']['url'])
        issue_id = r['transferIssue']['issue']['id']
        # TODO: Probably this is gitHub bug
        # Check this: https://github.com/orgs/community/discussions/60896
        if len(r['transferIssue']['issue']['assignees']['edges']) != 0:
            imessage.set_assigned(r['transferIssue']['issue']['assignees']['edges'][0]['node']['login'])
        logging.info(f'''Succeeded transferred Issue: {r['transferIssue']['issue']['url']}''')
    else:
        r = github.open_issue(repo_id, imessage.issue_title, imessage.get_gh_body(update))

        imessage.set_issue_url(r['createIssue']['issue']['url'])
        issue_id = r['createIssue']['issue']['id']
        logging.info(f'''Succeeded open Issue: {r['createIssue']['issue']['url']}''')
        if settings.GH_SCRUM_STATE:
            threading.Thread(target=github.add_to_scrum, args=(r['createIssue']['issue']['id'], )).start()

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('↩️', callback_data=f'quite_{issue_id}'),
                                      InlineKeyboardButton('🗄 ', callback_data=f'repos_start'),
                                      InlineKeyboardButton('👤', callback_data=f'members_start'),
                                      InlineKeyboardButton('❌', callback_data=f'close_{issue_id}')]])
    return keyboard, imessage.get_text()


def __set_assign(update: Update):
    assign_to_id = __get_action_value(update)
    issue_id = __search_issue_id_in_keyboard(update)
    imessage = TgIssueMessage(bot_html=update.callback_query.message.text_html)

    r = github.set_assignee(issue_id, assign_to_id)

    new_assigned = r['updateIssue']['issue']['assignees']['edges'][0]['node']['login']
    imessage.set_assigned(new_assigned)
    logging.info(f'Set assign to {new_assigned}')
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('↩️', callback_data=f'quite_{issue_id}'),
                                      InlineKeyboardButton('🗄 ', callback_data=f'repos_start'),
                                      InlineKeyboardButton('👤', callback_data=f'members_start'),
                                      InlineKeyboardButton('❌', callback_data=f'close_{issue_id}')]])
    return keyboard, imessage.get_text()


def __close_issue(update: Update):
    imessage = TgIssueMessage(bot_html=update.callback_query.message.text_html)
    issue_id = __search_issue_id_in_keyboard(update)

    r = github.close_issue(issue_id)

    assert type(r['closeIssue']['issue']['id']) is str
    text = imessage.get_close_message(update.callback_query.from_user.full_name)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Reopen', callback_data=f'reopen_{issue_id}')]])

    logging.info(f'Succeeded closed Issue: {imessage.issue_url}')
    return keyboard, text


def __reopen_issue(update: Update):

    issue_id = __search_issue_id_in_keyboard(update)

    r = github.reopen_issue(issue_id)

    issue_url = r['reopenIssue']['issue']['url']
    title = r['reopenIssue']['issue']['title']
    if len(r['reopenIssue']['issue']['assignees']['edges']) != 0:
        login = r['reopenIssue']['issue']['assignees']['edges'][0]['node']['login']
    else:
        login = None
    body = r['reopenIssue']['issue']['body'].split('\n> Issue open by')[0]

    imessage = TgIssueMessage()
    imessage.from_reopen(issue_url, title, body, login)

    if settings.GH_SCRUM_STATE:
        threading.Thread(target=github.add_to_scrum, args=(issue_id,)).start()

    logging.info(f'Succeeded Reopen Issue: {imessage.issue_url}')
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('Setup', callback_data=f'setup_{issue_id}')]])
    return keyboard, imessage.get_text()


def __get_action_value(update: Update):
    return update.callback_query.data.split('_', 1)[1]


def __search_issue_id_in_keyboard(update: Update):
    kb = update.callback_query.message.reply_markup.inline_keyboard
    issue_id = None
    for kb_row in kb:
        for kb_col in kb_row:
            if kb_col.callback_data.startswith(('quite_', 'close_', 'setup_', 'reopen_')) and \
                    kb_col.callback_data.split('_', 1)[1] != 'start':
                issue_id = kb_col.callback_data.split('_', 1)[1]
                return issue_id
    return issue_id
