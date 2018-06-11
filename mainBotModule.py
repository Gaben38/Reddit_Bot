from urllib.parse import urlparse
from urllib.parse import unquote
from bs4 import BeautifulSoup
import os
import praw
import time
import re
import requests
import bs4
import wikipedia
import threading
import sys
import glob
from datetime import datetime as dt
from checkPath import is_path_exists_or_creatable
from myExceptions import CommandDontExistException, CommandExistsException, BotDontExistException, BotExistsException
from pyzbar import pyzbar
from PIL import Image
from io import BytesIO
from configparser import NoSectionError
	
class RedditBot(threading.Thread):
	#reddit = None # через класс reddit идет вся работа с api
	subreddit = 'test' # сабреддит на котором бот будет просматривать комментарии
	bot_profile = "Default" # имя секции бота в praw.ini
	AUTHOR_USERNAME = 'Gaben38' # никнейм "администратора" бота, личные сообщения только от этого пользователя будут проверятся на команды управления
	
	TEXT_COMMAND_PREFIX = '!'
	TEXT_COMMAND_FILENAME_POSTFIX = '_commented.txt'
	TEXT_COMMANDS_DIRECTORYNAME = 'Commands'
	#text_commands = {} # словарь текстовых команд где ключ = имя команды, к которому относится список из 1 или 2 элементов, первый элемент - ответ на команду, второй(опциональный) элемент - помощь по команде
	
	ABOUT_COMMAND = 'about' # текст обязательной текстовой команды about
	ABOUT_TEXT = '*--- Бот создан /u/gaben38 в качестве дипломной работы ---*'
	ABOUT_HELP = 'Команда "об авторе"'
	HELP_COMMAND = 'help'
	HELP_HELP = '''Вики- и штрихкод-команды можно использовать посреди комментария, **тектовые команды необходимо использовать только в начале комментария.**\n\n
Для получения краткого содержания статьи википедии по ссылке, добавьте ее в комментарий в формате [[ссылка]].\n\n
Для получения краткого содержания статьи википедии по названию статьи, добавьте ее в комментарий в формате [[языковой поддомен|название статьи]]. *Языковой поддомен опционален, если неуказан, то по умолчанию берется с ru википедии.*\n\n
Для расшифровки штрихкодов в изображении, добавьте ссылку на изображение в комментарий в формате {{ссылка}}. *Поддерживается до 3(включительно) изображений в одном комментарии.*\n\n
Для получения информации по тектовой команде введите команду справки в формате !help <название тектсовой команды>\n\n
**Список текстовых команд:**\n\n'''
	stopper = None # флаг остановки для потока
	comm_lock = threading.RLock() # "мьютекс" для работы со словарем команд
	log_lock = threading.RLock() # "мьютекс" для работы с файлом лога
	
	WIKI_LOG_PATH = 'wiki_commented.txt' # название файла со списком комментариев на которые НЕ нужно отвечать (уже опубликован ответ на вики-команду)
	WIKI_HEADER = '**Краткое содержание статьи:**\n\n' # заголовок ответа на вики-команду
	WIKI_FOOTER = '\n\n*Содержание взято с wikipedia.org*\n\n*Содержание берется только для первой ссылке в комментии*\n\n*Бот создан /u/gaben38*' # окончание ответа на вики-команду
	WIKI_DISAMB_REPLY = 'Неявно определено название статьи.\n\nВозможно вы имели ввиду:\n\n' # заголовок комментария на случай если неявно дано название статьи
	WIKI_NO_PAGE_REPLY = '*Статьи с данным именем не найдено.*\n\nУдостоверьтесь, что вы правильно указали название.'
	WIKI_DEFAULT_LANG = 'ru' # языковой поддомен по умолчанию
	
	BARCODE_LOG_PATH = 'barcode_commented.txt' # название файла со списком комментариев на которые НЕ нужно отвечать (уже опубликован ответ на штрихкод-команду)
	BARCODE_LINKS_HEADER = '**Найдены следующие ссылки на изображения в нужном формате:**\n\n'
	BARCODE_NOLINKS_HEADER = '**Не найдены ссылки на изображения в нужном формате.**\n\n**Удостоверьтесь, что предоставленные ссылки являются прямыми ссылками на изображения в jpeg или png формате.**\n\n'
	BARCODE_FOUND_HEADER = 'В изображении найдены следующие шрихкоды:\n\n'
	BARCODE_NOTFOUND_HEADER = '*В изображении не были найдены шрихкоды.*\n\n'
	BARCODE_TABLE_TYPE_HEADER = 'Тип штрихкода'
	BARCODE_TABLE_CONTENT_HEADER = 'Содержимое'
	BARCODE_TABLE_FORMAT = '-|-'
	BARCODE_LINKS_PER_COMMENT_LIMIT = 3
	
	CONTROL_MESSAGES_PATH = 'ctrl_messages_replied.txt'
	CONTROL_STOP_COMMAND = 'stop'
	CONTROL_STOP_REPLY = 'Команда выключения успешно распознана.\n\n[Завершаю работу.](https://www.youtube.com/watch?v=Gb2jGy76v0Y)'
	CONTROL_ADDCMD_COMMAND = 'addcommand'
	CONTROL_ADDCMD_REPLY = 'Команда добавления типовой текстовой команды успешно распознана.\n\n**Новая команда:**\n\n'
	CONTROL_ADDCMD_DUPICATE_REPLY = 'Указанная типовая текстовая команда уже существует.\n\n'
	CONTROL_ADDCMD_INVALID_NAME = 'Неверное название профиля бота\n\nНазвание может содержать только символы подходящие для названия папки'
	CONTROL_REMOVECMD_COMMAND = 'removecommand'
	CONTROL_REMOVECMD_SUCC_REPLY = 'Команда удаления типовой текстовой команды успешно распознана.\n\n'
	CONTROL_REMOVECMD_NOTFOUND_REPLY = 'Указанная типовая текстовая команда не найдена.\n\n'
	
	ITERATION_TIMEOUT = 60 # секунд, таймаут после прохода последних 250 комментариев
	RESPONCE_TIMEOUT = 5 # секунд, таймаут после отправления ответа
	
	def __init__(self, bprofile, subrd): # конструктор бота, bot_profile - имя профиля бота в praw.ini
		super().__init__(name = bprofile)
		if not is_path_exists_or_creatable(pathname = bprofile):
			raise InvalidBotProfileName('Неверное название профиля бота\nНазвание может содержать только символы подходящие для названия папки')
			return
		self.bot_profile = str(bprofile)
		self.subreddit = subrd
		self.stopper = threading.Event()
		self.comm_lock = threading.RLock()
		self.refresh_command_dict()
		#print(self.text_commands)
		self.write_to_log('Логинюсь...\n')
		try:
			self.reddit = praw.Reddit(bprofile)
		except NoSectionError:
			#print('ВНИМАНИЕ: Попытка запусть бота с нервеными данными. Проверьте наличие секции в praw.ini'
			raise BotSectionNotFound('ВНИМАНИЕ: Попытка запусть бота с нервеными данными. Проверьте наличие секции в praw.ini')
		self.write_to_log('Залогинился как: {}\n'.format(self.reddit.user.me()))

	def join(self, timeout=None): # перегружаем метод join для остановки треда
		self.stopper.set()
		super().join(timeout)

	def get_wiki_page_title(self, url): # достает наименование статьи из ссылки на википедию
		parsed = urlparse(url)
		wiki_id = parsed.path.strip("/wiki")
		page_title = wiki_id.split('/',1)[0] # убираем лишние слэши
		page_title = wiki_id.split('#',1)[0] # убираем из ссылки подзаголовок
		final_title = unquote(page_title.replace('_', ' ')) # заменяем подеркивания на пробелы
		self.write_to_log('Пропарсил ссылку: ' + url)
		self.write_to_log('Получил название статьи: ' + final_title)
		return final_title
	
	def write_to_log(self, message):
		'''
		Функция записи в лог
		message - строка для записи в лог
		Файл лога log.txt находится в папке бота
		'''
		with self.log_lock:
			if not message.endswith('\n'):
				message+= '\n'
			self.check_bot_directory()
			bot_directory = str(self.bot_profile)
			log_file = open(os.path.join(bot_directory, 'log.txt'), 'a+')
			str_time = dt.now().strftime('%Y-%m-%d %H:%M:%S')
			log_file.write('[' + str_time + ']' + ': ' + message)
			log_file.close()

	def check_bot_directory(self): # проверка существования и/или создание папки бота и папки команд
		bot_directory = str(self.bot_profile)
		comm_directory = os.path.join(bot_directory, self.TEXT_COMMANDS_DIRECTORYNAME)
		if not os.path.exists(bot_directory):
			os.makedirs(bot_directory)
		if not os.path.exists(comm_directory):
			os.makedirs(comm_directory)

	def refresh_command_dict(self):
		'''
		Функция обновления словаря для типовых текстовых команд
		Все типовые тектовые команды, кроме about и help, хранятся в виде файлов в папке Commands в папке бота
		Название .txt файла = название команды, его содержимое = ответ на команду
		Так же опциональный файл с расширением .help и тем же названием что и .txt содержит в себе помощь по команде
		'''
		with self.comm_lock:
			bot_directory = str(self.bot_profile)
			comm_directory = os.path.join(bot_directory, self.TEXT_COMMANDS_DIRECTORYNAME)
			self.write_to_log('Рефрешу текстовые команды для профиля "' + self.bot_profile)
			self.text_commands = dict()
			self.text_commands.update({self.ABOUT_COMMAND : [self.ABOUT_TEXT, self.ABOUT_HELP]})
			self.text_commands.update({self.HELP_COMMAND : ["", self.HELP_HELP]})
			self.check_bot_directory()
			for filename in glob.glob(os.path.join(comm_directory, '*.txt')):
				base_filename = os.path.splitext(os.path.basename(filename))[0] # имя файла без .txt = команда
				file = open(filename, 'r')
				text = file.read() # содержимое = ответ на нее
				file.close()
				help_filename = os.path.join(comm_directory, base_filename + '.help')
				if os.path.exists(help_filename):
					file = open(help_filename, 'r')
					help_text = file.read() # содержимое (имя команды).help = помощь по команде
					file.close()
					self.text_commands.update({base_filename : [text, help_text]})
				else:
					self.text_commands.update({base_filename : [text]})
	
	def add_command(self, comm_name: str, comm_text: str, comm_help: str = None):
		'''
		Функция добавления типовой текстовой команды
		comm_name - имя команды
		comm_text - ответ бота на команду
		comm_help - помощь по команде(опциональный параметр)
		'''
		with self.comm_lock:
			bot_directory = str(self.bot_profile)
			comm_directory = os.path.join(bot_directory, self.TEXT_COMMANDS_DIRECTORYNAME)
			self.check_bot_directory()
			if comm_name in self.text_commands:
				raise CommandExistsException('Текстовая команда с таким именем уже существует')
				#return
			new_comm_file = open(os.path.join(comm_directory, comm_name + '.txt'), 'w')
			new_comm_file.write(comm_text)
			new_comm_file.close()
			if comm_help is not None:
				new_help_file = open(os.path.join(comm_directory, comm_name + '.help'), 'w')
				new_help_file.write(comm_help)
				new_help_file.close()
				self.write_to_log('Добавление команды {' + comm_name + ';' + comm_text + ';' + comm_help + '}')
			else:
				self.write_to_log('Добавление команды {' + comm_name + ';' + comm_text + '}')
			self.refresh_command_dict()

	def remove_command(self, comm_name):
		'''
		Функция удаления типовой тектовой команды
		comm_name - имя команды
		'''
		with self.comm_lock:
			bot_directory = str(self.bot_profile)
			comm_directory = os.path.join(bot_directory, self.TEXT_COMMANDS_DIRECTORYNAME)
			self.check_bot_directory()
			if comm_name not in self.text_commands:
				raise CommandDontExistException('Не найдена команда "' + comm_name + '"')
				#return
			if os.path.exists(os.path.join(comm_directory, comm_name + '.txt')): # если есть файл с командой и ответом удаляем его
				os.remove(os.path.join(comm_directory, comm_name + '.txt'))
			if os.path.exists(os.path.join(comm_directory, comm_name + '.help')): # если есть файл с помощью по команде удаляем его
				os.remove(os.path.join(comm_directory, comm_name + '.help'))
			self.write_to_log('Удаление команды "' + comm_name + '"')
			self.refresh_command_dict()
		
	def check_wiki_link_command(self, comment):
		'''
		Функция проверки на команду краткого содержания по ссылке на статью википедии 
		comment - комментарий для проверки
		return True - найдена команда в нужном формате и успешно отправлен ответ 
		return False - не найден либо ошибка при ответе
		'''
		history_filename = os.path.join(self.bot_profile, self.WIKI_LOG_PATH)
		if not os.path.exists(history_filename):
			open(history_filename, 'w').close()
		history_file = open(history_filename, 'r')
		if comment.id not in history_file.read().splitlines():
			match = re.findall('.*\[\[(http[s]?:\/\/([a-z]{1,3})\.wikipedia\.org\/wiki\/.+)\]\].*', comment.body)
			if match:
				self.write_to_log('Вики-ссылка найдена в комментарии с id: ' + comment.id)
				url = match[0][0] # ссылка на статью
				lang = match[0][1] # языковой поддомен
				if lang not in wikipedia.languages():
					self.write_to_log('Дан неверный языковой поддомен "' + lang + '" в ссылке ' + url)
					return False
				try:
					page_title = self.get_wiki_page_title(url)
					wikipedia.set_lang(lang)
					summary = self.WIKI_HEADER + wikipedia.summary(page_title) + self.WIKI_FOOTER
				except wikipedia.exceptions.DisambiguationError as e:
					summary = self.WIKI_DISAMB_REPLY
					for possible_title in e.options:
						summary+= possible_title + '\n\n'
				except Exception as e:
					print('Возникло исключение: ' + str(e) + '\n')
					history_file.close()
					return False
				comment.reply(summary)
				history_file.close()
				history_file = open(history_filename, 'a+')
				history_file.write(comment.id + '\n')
				history_file.close()
				self.write_to_log('Успешно отправил ответ на вики-команду и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
				time.sleep(self.RESPONCE_TIMEOUT)
				return True
			else:
				history_file.close()
				return False
		else:
			history_file.close()
			self.write_to_log('Повтор комментария, можно не отвечать')
			return True
	
	def check_wiki_text_command(self, comment):
		'''
		Функция проверки на команду краткого содержания в формате [[языковой префикс|название статьи]], префикс опционален
		comment - комментарий для проверки
		return True - найдена команда в нужном формате и успешно отправлен ответ 
		return False - не найден либо ошибка при ответе
		'''
		history_filename = os.path.join(self.bot_profile, self.WIKI_LOG_PATH)
		if not os.path.exists(history_filename):
			open(history_filename, 'w').close()
		history_file = open(history_filename, 'r')
		if comment.id not in history_file.read().splitlines():
			match = re.findall('.*\[\[(\w{2,3}\|)?(\w+)\]\].*', comment.body)
			if match:
				self.write_to_log('Вики-ссылка найдена в комментарии с id: ' + comment.id)
				lang = match[0][0] # языковой поддомен
				title = match[0][1] # название статьи
				if lang != '':
					lang = lang.replace("|", "")
					if lang not in wikipedia.languages():
						self.write_to_log('Дан неверный языковой поддомен "' + lang + '" вместе в именем статьи ' + title)
						history_file.close()
						return False
				else:
					lang = self.WIKI_DEFAULT_LANG
				try:
					wikipedia.set_lang(lang)
					summary = wikipedia.summary(title)
				except wikipedia.exceptions.DisambiguationError as e:
					reply = self.WIKI_DISAMB_REPLY
					for possible_title in e.options:
						reply+= possible_title + '\n\n'
					comment.reply(reply)
					history_file.close()
					history_file = open(history_filename, 'a+')
					history_file.write(comment.id + '\n')
					history_file.close()
					self.write_to_log('Ответил на вики-команду с неопределенным названием статьи и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
					time.sleep(self.RESPONCE_TIMEOUT)
					return True
				except wikipedia.exceptions.PageError:
					reply = self.WIKI_NO_PAGE_REPLY
					comment.reply(reply)
					history_file.close()
					history_file = open(history_filename, 'a+')
					history_file.write(comment.id + '\n')
					history_file.close()
					self.write_to_log('Ответил на вики-команду с несуществующим названием статьи и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
					time.sleep(self.RESPONCE_TIMEOUT)
					return True
				except Exception as e:
					print('Возникло исключение: ' + str(e) + '\n')
					history_file.close()
					return False
				else:
					comment.reply(self.WIKI_HEADER + summary + self.WIKI_FOOTER)
					history_file.close()
					history_file = open(history_filename, 'a+')
					history_file.write(comment.id + '\n')
					history_file.close()
					self.write_to_log('Успешно отправил ответ на вики-команду и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
					time.sleep(self.RESPONCE_TIMEOUT)
					return True
			else:
				history_file.close()
				return False
		else:
			history_file.close()
			self.write_to_log('Повтор комментария с вики-командой, можно не отвечать')
			return True
				
	def check_text_commands(self, comment, txt_comms):
		'''
		Функция проверки комментария на типовые тектовые команды
		comment - комментарий для проверки
		txt_comms - словарь типовых тектовых команд
		return True - найдена команда в нужном формате и успешно отправлен ответ 
		return False - не найден либо ошибка при ответе
		'''
		with self.comm_lock:
			for command, values  in txt_comms.items():
				if command != self.HELP_COMMAND:
					regexp = '\\' + self.TEXT_COMMAND_PREFIX + command + '.*'
				else:
					regexp = '^\\' + self.TEXT_COMMAND_PREFIX + command + '( \w+)?[ \n]?.*$'
				match = re.findall(regexp, comment.body)
				if match:
					self.write_to_log('Найдена текстовая команда "' + command + '"')
					history_filename = os.path.join(self.bot_profile, command + self.TEXT_COMMAND_FILENAME_POSTFIX)
					if not os.path.exists(history_filename):
						open(history_filename, 'w').close()
					history_file = open(history_filename, 'r')
					if comment.id not in history_file.read().splitlines():
						self.write_to_log('Отправляю ответ...')
						if command != self.HELP_COMMAND:
							responce = values[0] # values = [responce_text, help_text], help_text - опциональный
						else:
							found_comm = match[0]
							found_comm = found_comm.replace(' ', '')
							self.write_to_log('Запрошена справка по команде "' + found_comm + '"')
							responce = ''
							if found_comm != '':
								for tmp_command, tmp_values in txt_comms.items():
									if tmp_command == found_comm:
										try:
											responce = tmp_values[1]
										except IndexError:
											responce = 'Справка не найдена для команды "' + tmp_command + '"'
										break
								if responce == '':
									responce = 'Команда "' + found_comm + '" не найдена'
							else:
								responce = self.HELP_HELP
								for key in txt_comms.keys():
									responce+= '*' + key + '*\n\n'
						comment.reply(responce)
						history_file.close()
						history_file = open(history_filename, 'a+')
						history_file.write(comment.id + '\n')
						history_file.close()
						self.write_to_log('Успешно отправил ответ на текстовую команду"' + command + '" и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
						time.sleep(self.RESPONCE_TIMEOUT)
					else:
						history_file.close()
						self.write_to_log('Повтор комментария с типовой текстовой командой, можно не отвечать')
					return True
			return False

	def check_barcode_command(self, comment):
		'''
		Функция проверки комментария на штрихкод-команду
		comment - комментарий для проверки
		return True - найдена команда в нужном формате и успешно отправлен ответ 
		return False - не найден либо ошибка при ответе
		'''
		history_filename = os.path.join(self.bot_profile, self.BARCODE_LOG_PATH)
		if not os.path.exists(history_filename):
			open(history_filename, 'w').close()
		history_file = open(history_filename, 'r')
		if comment.id not in history_file.read().splitlines():
			match = re.findall('\{\{(http[s]?:\/\/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)\}\}', comment.body)
			if match:
				responce = self.BARCODE_LINKS_HEADER
				links_num = 0
				self.write_to_log('Штрихкод-команда найдена в комментарии с id: ' + str(comment.id))
				for url in match:
					if links_num >= self.BARCODE_LINKS_PER_COMMENT_LIMIT:
						break
					
					content_type = requests.head(url).headers.get('content-type')
					if(content_type == 'image/jpeg' or content_type == 'image/png'):
						self.write_to_log('Обрабатываю ссылку с изображением: ' + url)
						links_num += 1
						responce += '* ' + url + '\n\n'
						web_image = requests.get(url)
						img = Image.open(BytesIO(web_image.content))

						barcodes = pyzbar.decode(img)
						if not barcodes:
							responce += self.BARCODE_NOTFOUND_HEADER
							self.write_to_log('Штрихкодов не найдено')
						else:
							responce += self.BARCODE_TABLE_TYPE_HEADER + '|' + self.BARCODE_TABLE_CONTENT_HEADER + '\n' + self.BARCODE_TABLE_FORMAT + '\n'
							for barcode in barcodes:
								responce += barcode.type + '|' + barcode.data.decode("utf-8") + '\n'
							responce += '\n\n'
							self.write_to_log('Найдено и расшифровано штрихкодов: ' + str(len(barcodes)))
					else:
						continue
				self.write_to_log('Обработано ' + str(links_num) + ' ссылок на изображения для комментария с id:' + str(comment.id))
				if(links_num < 1):
					responce = self.BARCODE_NOLINKS_HEADER
				comment.reply(responce)
				history_file.close()
				history_file = open(history_filename, 'a+')
				history_file.write(comment.id + '\n')
				history_file.close()
				self.write_to_log('Успешно отправил ответ на шрихкод-команду и записал в историю, таймаут ' + str(self.RESPONCE_TIMEOUT) + ' сек.')
				time.sleep(self.RESPONCE_TIMEOUT)
				return True
			else:
				history_file.close()
				return False
		else:
			history_file.close()
			self.write_to_log('Повтор комментария со штрихкод-командой, можно не отвечать')
			return True
			
	def check_other_commands(self):
		'''
		Функция пустышка
		'''
		return True

	def check_control_messages(self, msg):
		'''
		Функция проверки личного сообщения на контроль-сообщения
		msg - личное сообщение для проверки
		return True - найдена контроль-сообщение в нужном формате и выполнено соответствующее действие
		return False - не найдено контроль-сообщений
		'''
		history_filename = os.path.join(self.bot_profile, self.CONTROL_MESSAGES_PATH)
		if not os.path.exists(history_filename):
			open(history_filename, 'w').close()
		history_file = open(history_filename, 'r')
		
		if msg.author.name == self.AUTHOR_USERNAME:
			if msg.id not in history_file.read().splitlines():
				if msg.body == self.TEXT_COMMAND_PREFIX + self.CONTROL_STOP_COMMAND: # стоп-сообщение
					self.stopper.set()
					self.write_to_log('Получение стоп-сообщения. Флаг остановки установлен.')
					msg.reply(self.CONTROL_STOP_REPLY)
					history_file.close()
					history_file = open(history_filename, 'a+')
					history_file.write(msg.id + '\n')
					history_file.close()
					return True
				else:
					match = re.findall('\\' + self.TEXT_COMMAND_PREFIX + self.CONTROL_ADDCMD_COMMAND + ' (\w{1,15}) ([^|]{1,128})(\|.{1,64})?', msg.body)
					if match:
						responce = ''
						try:
							if match[0][2]:
								help_text = match[0][2][1:] # удаление | из начала совпадения
								self.add_command(match[0][0], match[0][1], help_text)
								#self.write_to_log('Добавление команды {' + match[0][0] + ';' + match[0][1] + ';' + help_text + '}')
								responce = self.CONTROL_ADDCMD_REPLY + 'comm_name = ' + match[0][0] + '\n\ncomm_text = ' + match[0][1] + '\n\ncomm_help = ' + help_text
							else:
								self.add_command(match[0][0], match[0][1])
								#self.write_to_log('Добавление команды {' + match[0][0] + ';' + match[0][1] + '}')
								responce = self.CONTROL_ADDCMD_REPLY + 'comm_name = ' + match[0][0] + '\n\ncomm_text = ' + match[0][1] + '\n\nСправка по команде не указана.'
						except CommandExistsException:
							responce = self.CONTROL_ADDCMD_DUPICATE_REPLY
							self.write_to_log('Запрос на добавление уже сущесвующей команды "' + match[0][0] + '"')
						msg.reply(responce)
						history_file.close()
						history_file = open(history_filename, 'a+')
						history_file.write(msg.id + '\n')
						history_file.close()
						return True
					else:
						match = re.findall('\\' + self.TEXT_COMMAND_PREFIX + self.CONTROL_REMOVECMD_COMMAND + ' (\w{1,15})', msg.body) # удалить команду
						if match:
							cmd = match[0]
							responce = ''
							try:
								self.remove_command(cmd)
								#self.write_to_log('Удаление команды "' + cmd + '"')
								responce = self.CONTROL_REMOVECMD_SUCC_REPLY
							except CommandDontExistException:
								self.write_to_log('Запрос на удаление несуществующей команды "' + cmd + '"')
								responce = self.CONTROL_REMOVECMD_NOTFOUND_REPLY
							msg.reply(responce)
							history_file.close()
							history_file = open(history_filename, 'a+')
							history_file.write(msg.id + '\n')
							history_file.close()
							return True
						else:
							history_file.close()
							return False
			else:
				history_file.close()
				return False
		else:
			history_file.close()
			return False
				

	def run(self):
		'''
		Основной цикл бота
		'''
		self.stopper.clear()
		while not self.stopper.is_set(): # пока не установлен флаг остановки
			self.write_to_log('Беру 250 комментариев...\n')
			for comment in self.reddit.subreddit(self.subreddit).comments(limit = 250): # берется 250 последних комментариев из сабреддита
				if comment.author.name != self.reddit.user.me(): # если автор - не этот бот
					if not self.check_wiki_link_command(comment): # проверяем на вики-команду по ссылке, если не подошло, то
						if not self.check_wiki_text_command(comment): # проверяем на вики-команду в тектовом формате, если не подошло, то
							if not self.check_text_commands(comment, self.text_commands): # проверяем на типовые тектовые команды, если не подошло, то
								if not self.check_barcode_command(comment): # проверяем на шрихкод-команду, если не подошло, то
									if self.check_other_commands(): # другие команды
										pass
			for msg in self.reddit.inbox.messages(limit = 25):
				if self.check_control_messages(msg):
					break;
			self.write_to_log('Итерация прошла, жду ' + str(self.ITERATION_TIMEOUT) + ' сек.')
			#time.sleep(60)
			for i in range(self.ITERATION_TIMEOUT): # после каждой итерации идет таймаут в 60 сек., каждую секунду таймаута проверяется установлен ли флаг остановки
				time.sleep(1)
				if self.stopper.is_set():
					break

class BotController(object):
	'''
		Объект контроллера ботов
		Осуществляет управление ботами и предоставляет меню
	'''
	bot_threads = dict()
	controller_name = None
	clear_command = 'clear'
	
	MENU_PRINT_BOTS = 'Вывести список ботов'
	MENU_PRINT_BOTS_RUNNING = 'Запущен'
	MENU_PRINT_BOTS_STOPPED = 'Ожидает запуска'
	MENU_NO_BOTS = 'В распоряжении контроллера нет ни одного бота!'
	
	MENU_ADD_BOT = 'Добавить бота'
	MENU_ADD_BOT_ENTER_NAME = 'Введите имя секции бота в praw.ini: '
	MENU_ADD_BOT_ENTER_SUBREDDIT = 'Введите название сабреддита для бота: '
	MENU_ADD_BOT_SUCC = 'Бот успешно добавлен'
	
	MENU_REMOVE_BOT = 'Удалить бота'
	MENU_REMOVE_BOT_SUCC = 'Бот успешно удален'
	
	MENU_START_BOT = 'Запустить бота'
	MENU_START_BOT_SUCC = 'Бот успешно запущен'
	
	MENU_STOP_BOT = 'Остановить бота'
	MENU_STOP_BOT_SUCC = 'Бот успешно остановлен'
	
	MENU_ENTER_CMD_NAME = 'Введите имя команды: '
	MENU_ENTER_CMD_REPLY = 'Введите ответ на команду: '
	MENU_ENTER_CMD_HELP = 'Введите помощь по команде(намите enter если отсутсвует): '
	
	MENU_ADD_CMD = 'Добавить команду боту'
	
	MENU_ADD_CMD_SUCC = 'Команда успешно добавлена'
	MENU_REMOVE_CMD = 'Удалить команду боту'
	MENU_REMOVE_CMD_SUCC = 'Команда успешно удалена'
	
	MENU_EXIT_CMD = '!q'
	MENU_QUIT = 'Введите !q для завершения работы программы'
	
	MENU_SHUTTING_DOWN = '\nЗавершаю работу.\nОстанавливаю треды ботов...\n'
	MENU_PRESS_ANY_BUTTON = '\nНажмите Enter для продолжения.\n'
	
	def __init__(self, par_name = None):
		if par_name is not None:
			controller_name = par_name
		bot_threads = dict()
		if sys.platform == 'win32':
			clear_command = 'cls'
	
	def add_bot(self, bot_profile, subreddit):
		if bot_profile in self.bot_threads:
			raise BotExistsException('Бот этого профиля уже существует')
			#return False
		else:
			try:
				new_bot = RedditBot(bot_profile, subreddit)
				self.bot_threads.update({bot_profile : new_bot})
			except BotSectionNotFound:
				print('ВНИМАНИЕ: Попытка запусть бота с нервеными данными. Проверьте наличие секции в praw.ini')
			return True
	
	def remove_bot(self, bot_profile):
		if bot_profile not in self.bot_threads:
			raise BotDontExistException('Бот этого профиля не найден')
			#return False
		else:
			if self.bot_threads[bot_profile].is_alive():
				self.bot_threads[bot_profile].join()
			del self.bot_threads[bot_profile]
			return True
	
	def start_bot(self, bot_profile):
		if bot_profile not in self.bot_threads:
			raise BotDontExistException('Бот этого профиля не найден')
			#return False
		else:
			if not self.bot_threads[bot_profile].is_alive():
				try:
					self.bot_threads[bot_profile].start()
				except RuntimeError:
					subrd = self.bot_threads[bot_profile].subreddit
					self.remove_bot(bot_profile)
					self.add_bot(bot_profile, subrd)
					self.bot_threads[bot_profile].start()
			return True
		
	def stop_bot(self, bot_profile):
		if bot_profile not in self.bot_threads:
			raise BotDontExistException('Бот этого профиля не найден')
			#return False
		else:
			if self.bot_threads[bot_profile].is_alive():
				self.bot_threads[bot_profile].join()
			return True
	
	def get_bot(self, bot_profile):
		if bot_profile not in self.bot_threads:
			raise BotDontExistException('Бот этого профиля не найден')
			#return False
		else:
			return self.bot_threads.get(bot_profile)

	def stop_all(self):
		for bot_thread in self.bot_threads.values():
			if bot_thread.is_alive():
				bot_thread.join()
	
	def clear_console(self):
		os.system(self.clear_command)
			
	def show_menu(self):
		self.clear_console()
		running = True
		while running:
			print('1) ' + self.MENU_PRINT_BOTS + '\n')
			print('2) ' + self.MENU_ADD_BOT + '\n')
			print('3) ' + self.MENU_REMOVE_BOT + '\n')
			print('4) ' + self.MENU_START_BOT + '\n')
			print('5) ' + self.MENU_STOP_BOT + '\n')
			print('6) ' + self.MENU_ADD_CMD + '\n')
			print('7) ' + self.MENU_REMOVE_CMD + '\n')
			print(self.MENU_QUIT + '\n')
			
			try:
				temp = input()
				self.clear_console()
				if temp == self.MENU_EXIT_CMD:
					print(self.MENU_SHUTTING_DOWN)
					self.stop_all()
					running = False
					
				elif temp == '1':
					if not self.bot_threads:
						print(self.MENU_NO_BOTS + '\n')
						wait = input(self.MENU_PRESS_ANY_BUTTON)
					else:
						for bot_name in self.bot_threads.keys():
							state = self.MENU_PRINT_BOTS_RUNNING
							if self.bot_threads[bot_name].is_alive():
								state = self.MENU_PRINT_BOTS_RUNNING
							else:
								state = self.MENU_PRINT_BOTS_STOPPED
							print(bot_name + ' --- ' + state + '\n')
						wait = input(self.MENU_PRESS_ANY_BUTTON)
						
				elif temp == '2':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					subrd_name = input(self.MENU_ADD_BOT_ENTER_SUBREDDIT)
					try:
						self.add_bot(bot_name, subrd_name)
						print(self.MENU_ADD_BOT_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				elif temp == '3':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					try:
						self.remove_bot(bot_name)
						print(self.MENU_REMOVE_BOT_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				elif temp == '4':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					try:
						self.start_bot(bot_name)
						print(self.MENU_START_BOT_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				elif temp == '5':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					try:
						self.stop_bot(bot_name)
						print(self.MENU_STOP_BOT_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				elif temp == '6':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					cmd_name = input(self.MENU_ENTER_CMD_NAME)
					while not cmd_name:
						self.clear_console()
						cmd_name = input(self.MENU_ENTER_CMD_NAME)
					cmd_reply = input(self.MENU_ENTER_CMD_REPLY)
					while not cmd_reply:
						self.clear_console()
						cmd_reply = input(self.MENU_ENTER_CMD_REPLY)
					cmd_help = input(self.MENU_ENTER_CMD_HELP)		
					try:
						if cmd_help:
							self.bot_threads[bot_name].add_command(cmd_name, cmd_reply, cmd_help)
						else:
							self.bot_threads[bot_name].add_command(cmd_name, cmd_reply)
						print(self.MENU_ADD_CMD_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				elif temp == '7':
					bot_name = input(self.MENU_ADD_BOT_ENTER_NAME)
					cmd_name = input(self.MENU_ENTER_CMD_NAME)	
					try:
						self.bot_threads[bot_name].remove_command(cmd_name)
						print(self.MENU_REMOVE_CMD_SUCC)
					except:
						print("Возникла ошибка: ", sys.exc_info()[0])
					wait = input(self.MENU_PRESS_ANY_BUTTON)
					
				
			except KeyboardInterrupt:
				print(self.MENU_SHUTTING_DOWN)
				self.stop_all()
				running = False
				
			if running:
				self.clear_console()
	
def main():
	controller = BotController('test-controller')
	controller.add_bot('diplbot', 'test')
	controller.show_menu()

main()