# Marakulin Andrey https://github.com/Annndruha
# 2023
# This class used for parsing telegram message ann reformat for markdown
import re
import logging

from telegram.constants import ChatType


class TgIssueMessage:
    def __init__(self, text_html, from_user=False, from_reopen=False):
        self.issue_title = None
        self.issue_url = None
        self.repo_name = None
        self.repo_url = None
        self.assigned = None
        self.assigned_url = None
        self.comment = ''
        self.github_comment = None
        if from_user and from_reopen:
            raise ValueError('Recreate issue class possible with only one source: from bot, from_user or from_reopen')
        if from_user:
            self.__parse_text(text_html)
        elif from_reopen:
            self.__parse_reopen_text(text_html)
        else:
            self.__parse_bot_text(text_html)

    @staticmethod
    def __extract_href(raw_text):
        match = re.search(r'href=[\'"]?([^\'" >]+)', raw_text)
        if match:
            url = match.group(1)
            match = re.search(r'>(.*?)</a>', raw_text)
            text = match.group(1) if match else None
            return url, text
        return None, raw_text

    @staticmethod
    def __replacements(text):
        d = {'<span class="tg-spoiler">': '', '</span>': '', '&quot;': '"', "&#x27;": "'", '\n</b>': '</b>\n',
             '\n</i>': '</i>\n', '\n</u>': '</u>\n', '\n</s>': '</s>\n', '\n</a>': '</a>\n', '\n</pre>': '</pre>\n',
             '<pre>': '```', '</pre>': '\n```', '\n</code>': '</code>\n'}
        for k, v in d.items():
            text = text.replace(k, v).replace(k, v).replace(k, v)
        return text

    @staticmethod
    def __get_link_to_telegram_message(update):
        if update.callback_query.message.chat.type == ChatType.SUPERGROUP:
            message_thread_id = update.callback_query.message.message_thread_id
            message_thread_id = 1 if message_thread_id is None else message_thread_id  # If 'None' set '1'
            chat_id = str(update.callback_query.message.chat_id)
            message_id = update.callback_query.message.message_id
            return f"""<a href="https://t.me/c/{chat_id[4:]}/{message_thread_id}/{message_id}">telegram message.</a>"""
        elif update.callback_query.message.chat.type == ChatType.GROUP:
            return 'group-chat message.'
        elif update.callback_query.message.chat.type == ChatType.PRIVATE:
            return 'personal telegram message.'
        else:
            logging.warning(f"Chat {update.callback_query.message.chat_id} not a supergroup, can't create a msg link.")
            return 'telegram message.'

    def get_gh_body(self, update):
        link_to_msg = self.__get_link_to_telegram_message(update)

        text = self.comment
        matches = re.findall(r'(<code>)([\s\S]*?)(</code>)', text)
        for m in matches:
            s = ''.join(m)
            if '\n' in s:
                text = text.replace(s, s.replace('<code>', '```\n').replace('</code>', '\n```\n'))
            else:
                text = text.replace(s, s.replace('<code>', '`').replace('</code>', '`'))

        return text + f'\n> Issue open by {update.callback_query.from_user.full_name} via {link_to_msg}'

    def __parse_text(self, text):
        text = self.__replacements(text)
        if len(text.split('\n')) == 1:
            self.issue_title = text
            self.comment = ''
        else:
            self.issue_title = text.split('\n')[0]
            self.comment = '\n'.join(text.split('\n')[1:])

    def __parse_reopen_text(self, text):
        self.issue_url, self.issue_title = self.__extract_href(text)
        self.set_issue_url(self.issue_url)

    def __parse_bot_text(self, text):
        text = self.__replacements(text)
        st = text.split('\n')
        self.issue_url, self.issue_title = self.__extract_href(st[0].replace('🏷 ', ''))
        self.repo_url, self.repo_name = self.__extract_href(st[1].replace('🗄 ', '').replace('⚠️ ', ''))
        self.assigned_url, self.assigned = self.__extract_href(st[2].replace('👤 ', ''))
        if len(st) > 3:
            self.comment = '\n'.join(st[3:])

    def get_close_message(self, closer_name):
        return f'Issue <a href="{self.issue_url}">{self.issue_title}</a> closed by {closer_name}'

    def set_issue_url(self, issue_url):
        self.issue_url = issue_url
        self.repo_name = issue_url.split('/')[-3]
        self.repo_url = issue_url.split('/issues/')[0]

    def set_assigned(self, assigned):
        self.assigned = assigned
        self.assigned_url = f'https://github.com/{assigned}'

    def get_text(self):
        text = ''
        if self.issue_url:
            text += f'🏷 <a href="{self.issue_url}">{self.issue_title}</a>'
        else:
            text += '🏷 ' + self.issue_title

        if self.repo_url:
            text += f'\n🗄 <a href="{self.repo_url}">{self.repo_name}</a>'
        else:
            text += '\n⚠️ No repo'

        if self.assigned_url:
            text += f'\n👤 <a href="{self.assigned_url}">{self.assigned}</a>'
        else:
            text += '\n👤 No assigned'

        if self.comment:
            text += f'\n{self.comment}'

        return text
